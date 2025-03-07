import logging
from typing import Dict
import urllib3
# pylint: disable=import-error
import requests
# pylint: disable=import-error
from requests.adapters import HTTPAdapter, Retry

from bookstack_file_exporter.config_helper.models import HttpConfig

log = logging.getLogger(__name__)

# disable TLS warnings if using verify_ssl=false
urllib3.disable_warnings()

class HttpHelper:
    """
    HttpHelper provides an http request helper with config stored and retries built in

    Args:
        :headers: <Dict[str, str]> = all headers to use for http requests
        :config: <HttpConfig> = Configuration with user inputs for http requests

    Returns:
        :HttpHelper: instance with methods to help with http requests.
    """
    def __init__(self, headers: Dict[str, str],
                 config: HttpConfig):
        self.backoff_factor = config.backoff_factor
        self.retry_codes = config.retry_codes
        self.retry_count = config.retry_count
        self.http_timeout = config.timeout
        self.verify_ssl = config.verify_ssl
        self._headers = headers

    # more details on options: https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html
    def http_get_request(self, url: str) -> requests.Response:
        """make http requests and return response object"""
        url_prefix = self.should_verify(url)
        try:
            with requests.Session() as session:
                # {backoff factor} * (2 ** ({number of previous retries}))
                # {raise_on_status} if status falls in status_forcelist range
                #  and retries have been exhausted.
                # {status_force_list} 413, 429, 503 defaults are overwritten with additional ones
                retries = Retry(total=self.retry_count,
                                backoff_factor=self.backoff_factor,
                                raise_on_status=True,
                                status_forcelist=self.retry_codes)
                session.mount(url_prefix, HTTPAdapter(max_retries=retries))
                response = session.get(url, headers=self._headers, verify=self.verify_ssl,
                                       timeout=self.http_timeout)
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

    @staticmethod
    def should_verify(url: str) -> str:
        """check if http or https"""
        if url.startswith("https"):
            return "https://"
        return "http://"
