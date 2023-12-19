import logging
from typing import Dict
# pylint: disable=import-error
import requests
# pylint: disable=import-error
from requests.adapters import HTTPAdapter, Retry

log = logging.getLogger(__name__)

def http_get_request(url: str, headers: Dict[str, str],
                     verify_ssl: bool, timeout: int = 30) -> requests.Response:
    """make http requests and return response object"""
    url_prefix = should_verify(url)
    try:
        with requests.Session() as session:
            # {backoff factor} * (2 ** ({number of previous retries}))
            # {raise_on_status} if status falls in status_forcelist range
            #  and retries have been exhausted.
            # {status_force_list} 429 is supposed to be included
            retries = Retry(total=3,
                            backoff_factor=0.5,
                            raise_on_status=True,
                            status_forcelist=[ 500, 502, 503, 504 ])
            session.mount(url_prefix, HTTPAdapter(max_retries=retries))
            response = session.get(url, headers=headers, verify=verify_ssl, timeout=timeout)
    except Exception as req_err:
        log.error("Failed to make request for %s", url)
        raise req_err
    try:
        #raise_for_status() throws an exception on codes 400-599
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # this means it either exceeded 50X retries in `http_get_request` handler
        # or it returned a 40X which is not expected
        log.error("Bookstack request failed with status code: %d on url: %s",
                   response.status_code, url)
        raise e
    return response

def should_verify(url: str) -> str:
    """check if http or https"""
    if url.startswith("https"):
        return "https://"
    return "http://"
