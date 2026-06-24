# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access
"""Unit tests for HttpHelper in bookstack_file_exporter.common.util."""
import logging

import pytest
import requests
import responses
from responses import matchers
from requests.adapters import DEFAULT_POOLSIZE

from bookstack_file_exporter.common.util import HttpHelper
from bookstack_file_exporter.config_helper.models import HttpConfig

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
    assert not result
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
# http_get_request — error responses
# ---------------------------------------------------------------------------

@responses.activate
@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
def test_http_get_request_non_2xx_raises_http_error(http_config, status_code, caplog):
    """Non-2xx responses raise HTTPError (retry_count=0 so no retries)."""
    caplog.set_level(logging.ERROR, logger="bookstack_file_exporter.common.util")
    client = HttpHelper(headers={}, config=http_config)
    responses.get(
        f"{BASE}/books",
        status=status_code,
    )
    with pytest.raises(requests.exceptions.HTTPError):
        client.http_get_request(f"{BASE}/books")
    # confirm the error log was emitted with the status code
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(str(status_code) in r.getMessage() for r in error_logs)


# ---------------------------------------------------------------------------
# http_get_request — retry logic
# ---------------------------------------------------------------------------

def _retry_config(retry_count=2, retry_codes=None):
    """Helper to build an HttpConfig with retries enabled."""
    return HttpConfig(
        timeout=10,
        verify_ssl=True,
        retry_count=retry_count,
        backoff_factor=0,
        retry_codes=retry_codes or [500, 502, 503],
    )


@responses.activate
def test_http_get_request_retries_500_then_succeeds():
    """500 in retry_codes → retried; eventual 200 returned."""
    client = HttpHelper(headers={}, config=_retry_config(retry_count=3))
    responses.get(f"{BASE}/books", status=500)
    responses.get(f"{BASE}/books", status=500)
    responses.get(f"{BASE}/books", json={"data": [], "total": 0}, status=200)
    response = client.http_get_request(f"{BASE}/books")
    assert response.status_code == 200


@responses.activate
def test_http_get_request_retries_exhausted_raises():
    """500 in retry_codes; exhausted retries → exception raised."""
    client = HttpHelper(headers={}, config=_retry_config(retry_count=1))
    # 1 retry = 2 attempts total; register 3 responses to be safe
    responses.get(f"{BASE}/books", status=500)
    responses.get(f"{BASE}/books", status=500)
    responses.get(f"{BASE}/books", status=500)
    # urllib3 Retry with raise_on_status=True surfaces exhaustion as
    # requests.exceptions.RetryError (verified with requests 2.32.3, urllib3 1.26.20).
    with pytest.raises(requests.exceptions.RetryError):
        client.http_get_request(f"{BASE}/books")


@responses.activate
def test_http_get_request_does_not_retry_non_retryable_code():
    """404 not in retry_codes → fails immediately, no retries."""
    client = HttpHelper(headers={}, config=_retry_config(retry_count=3))
    responses.get(f"{BASE}/books", status=404)
    with pytest.raises(requests.exceptions.HTTPError):
        client.http_get_request(f"{BASE}/books")
    # only one HTTP call should have been made (no retries for 404)
    assert len(responses.calls) == 1


# ---------------------------------------------------------------------------
# session reuse
# ---------------------------------------------------------------------------

@responses.activate
def test_http_get_request_returns_response(http_config):
    responses.add(responses.GET, "https://wiki.test.example/api/books",
                  json={"data": []}, status=200)
    helper = HttpHelper({"Authorization": "Token x:y"}, http_config)
    resp = helper.http_get_request("https://wiki.test.example/api/books")
    assert resp.status_code == 200
    assert resp.json() == {"data": []}


@responses.activate
def test_http_get_request_reuses_session(http_config, monkeypatch):
    """HttpHelper builds a single requests.Session and reuses it across calls.

    Asserts the contract (one Session constructed for N requests) by spying the
    constructor, rather than poking the private _session attribute — so it
    survives an internal rename.
    """
    responses.add(responses.GET, "https://wiki.test.example/api/books",
                  json={"data": []}, status=200)
    real_session_cls = requests.Session
    built = []

    def _spy(*args, **kwargs):
        session = real_session_cls(*args, **kwargs)
        built.append(session)
        return session

    monkeypatch.setattr(
        "bookstack_file_exporter.common.util.requests.Session", _spy)

    helper = HttpHelper({}, http_config)
    helper.http_get_request("https://wiki.test.example/api/books")
    helper.http_get_request("https://wiki.test.example/api/books")

    assert len(built) == 1  # one Session constructed, reused across calls


@responses.activate
def test_session_does_not_echo_server_cookies(http_config):
    """Stateless token auth: a Set-Cookie from BookStack must not be echoed back.

    Regression guard — the reused Session previously persisted BookStack's
    `bookstack_session` cookie and sent it on later requests, causing intermittent
    403s ("owner of the used API token does not have permission") mid-export.
    """
    responses.add(responses.GET, "https://wiki.test.example/api/books",
                  json={"data": []}, status=200,
                  headers={"Set-Cookie": "bookstack_session=abc123; path=/; httponly"})
    responses.add(responses.GET, "https://wiki.test.example/api/books",
                  json={"data": []}, status=200)

    helper = HttpHelper({}, http_config)
    helper.http_get_request("https://wiki.test.example/api/books")
    helper.http_get_request("https://wiki.test.example/api/books")

    # the second request must NOT carry a Cookie header echoing the server session
    assert "Cookie" not in responses.calls[1].request.headers


# ---------------------------------------------------------------------------
# connection pool sizing
# ---------------------------------------------------------------------------

def test_pool_maxsize_floors_at_requests_default_for_low_workers():
    helper = HttpHelper({}, HttpConfig(), export_workers=4)
    adapter = helper._session.get_adapter("https://example.com")
    # Floor tracks requests' own DEFAULT_POOLSIZE (see common/util.py), not a literal.
    assert adapter._pool_maxsize == DEFAULT_POOLSIZE


def test_pool_maxsize_scales_with_export_workers():
    helper = HttpHelper({}, HttpConfig(), export_workers=16)
    adapter = helper._session.get_adapter("https://example.com")
    assert adapter._pool_maxsize == 16


def test_export_workers_defaults_to_one_when_omitted():
    helper = HttpHelper({}, HttpConfig())
    adapter = helper._session.get_adapter("https://example.com")
    assert adapter._pool_maxsize == DEFAULT_POOLSIZE
