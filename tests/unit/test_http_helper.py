"""Unit tests for HttpHelper in bookstack_file_exporter.common.util."""
import pytest
import requests
import responses
from responses import matchers

from bookstack_file_exporter.common.util import HttpHelper

BASE = "https://wiki.test.example/api"


# ---------------------------------------------------------------------------
# http_get_all
# ---------------------------------------------------------------------------

@responses.activate
def test_http_get_all_single_page_returns_all(http_config):
    client = HttpHelper(headers={}, config=http_config)
    responses.get(
        f"{BASE}/books",
        json={"data": [{"id": 1}, {"id": 2}, {"id": 3}], "total": 3},
    )
    result = client.http_get_all(f"{BASE}/books")
    assert len(result) == 3
    assert result[0]["id"] == 1
    assert len(responses.calls) == 1


@responses.activate
def test_http_get_all_exact_boundary(http_config):
    """total == count → single call, all 500 items returned."""
    client = HttpHelper(headers={}, config=http_config)
    items = [{"id": i} for i in range(500)]
    responses.get(
        f"{BASE}/books",
        json={"data": items, "total": 500},
    )
    result = client.http_get_all(f"{BASE}/books")
    assert len(result) == 500
    assert len(responses.calls) == 1


@responses.activate
def test_http_get_all_multiple_pages(http_config):
    """750 total across two pages; verifies offset values."""
    client = HttpHelper(headers={}, config=http_config)
    page1 = [{"id": i} for i in range(500)]
    page2 = [{"id": i} for i in range(500, 750)]

    responses.get(
        f"{BASE}/books",
        match=[matchers.query_param_matcher({"count": "500", "offset": "0"})],
        json={"data": page1, "total": 750},
    )
    responses.get(
        f"{BASE}/books",
        match=[matchers.query_param_matcher({"count": "500", "offset": "500"})],
        json={"data": page2, "total": 750},
    )

    result = client.http_get_all(f"{BASE}/books")
    assert len(result) == 750
    assert len(responses.calls) == 2
    # Verify offsets in actual request URLs
    assert "offset=0" in responses.calls[0].request.url
    assert "offset=500" in responses.calls[1].request.url


@responses.activate
def test_http_get_all_empty_result(http_config):
    client = HttpHelper(headers={}, config=http_config)
    responses.get(f"{BASE}/books", json={"data": [], "total": 0})
    result = client.http_get_all(f"{BASE}/books")
    assert result == []
    assert len(responses.calls) == 1


@responses.activate
def test_http_get_all_empty_batch_mid_pagination_short_circuits(http_config):
    """Empty second batch with total still high → loop must terminate, not spin."""
    client = HttpHelper(headers={}, config=http_config)
    page1 = [{"id": i} for i in range(500)]

    responses.get(
        f"{BASE}/books",
        match=[matchers.query_param_matcher({"count": "500", "offset": "0"})],
        json={"data": page1, "total": 1000},
    )
    responses.get(
        f"{BASE}/books",
        match=[matchers.query_param_matcher({"count": "500", "offset": "500"})],
        json={"data": [], "total": 1000},
    )

    result = client.http_get_all(f"{BASE}/books")
    assert len(result) == 500
    assert len(responses.calls) == 2


@responses.activate
def test_http_get_all_preserves_existing_query_params(http_config):
    """Extra query params (e.g. sort) survive alongside count and offset."""
    client = HttpHelper(headers={}, config=http_config)
    responses.get(
        f"{BASE}/books",
        match=[matchers.query_param_matcher(
            {"sort": "+name", "count": "500", "offset": "0"},
            strict_match=True,
        )],
        json={"data": [{"id": 1}], "total": 1},
    )
    result = client.http_get_all(f"{BASE}/books?sort=%2Bname")
    assert len(result) == 1
    assert len(responses.calls) == 1


@responses.activate
def test_http_get_all_strips_caller_count_offset(http_config):
    """count/offset supplied by caller are replaced by HttpHelper's own values."""
    client = HttpHelper(headers={}, config=http_config)
    responses.get(
        f"{BASE}/chapters",
        match=[matchers.query_param_matcher(
            {"count": "500", "offset": "0"},
            strict_match=True,
        )],
        json={"data": [], "total": 0},
    )
    client.http_get_all(f"{BASE}/chapters?count=10&offset=5")
    assert len(responses.calls) == 1


@responses.activate
def test_http_get_all_custom_count_parameter(http_config):
    """Custom count=50 is forwarded to the URL."""
    client = HttpHelper(headers={}, config=http_config)
    responses.get(
        f"{BASE}/pages",
        match=[matchers.query_param_matcher({"count": "50", "offset": "0"})],
        json={"data": [{"id": 1}], "total": 1},
    )
    result = client.http_get_all(f"{BASE}/pages", count=50)
    assert len(result) == 1
    assert len(responses.calls) == 1


# ---------------------------------------------------------------------------
# http_get_request
# ---------------------------------------------------------------------------

@responses.activate
def test_http_get_request_200_returns_response(http_config):
    client = HttpHelper(headers={}, config=http_config)
    responses.get(f"{BASE}/books", json={"data": [], "total": 0}, status=200)
    resp = client.http_get_request(f"{BASE}/books")
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "total": 0}


@responses.activate
def test_http_get_request_404_raises_http_error(http_config):
    """retry_count=0 in fixture so 404 raises immediately."""
    client = HttpHelper(headers={}, config=http_config)
    responses.get(f"{BASE}/missing", status=404)
    with pytest.raises(requests.exceptions.HTTPError):
        client.http_get_request(f"{BASE}/missing")


# ---------------------------------------------------------------------------
# should_verify (static method)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://x.com", "https://"),
    ("http://x.com", "http://"),
    ("https://example.org/api/path", "https://"),
])
def test_should_verify(url, expected):
    assert HttpHelper.should_verify(url) == expected
