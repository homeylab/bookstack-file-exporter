import logging
import os
from datetime import datetime
from http.cookiejar import DefaultCookiePolicy
from typing import TypeVar
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
import urllib3
# pylint: disable=import-error
import requests
# pylint: disable=import-error
from requests.adapters import HTTPAdapter, Retry, DEFAULT_POOLSIZE
from croniter import croniter
from pydantic import TypeAdapter, ValidationError

from bookstack_file_exporter.config_helper.models import HttpConfig

T = TypeVar("T")

log = logging.getLogger(__name__)

# Base name for everything the tool creates: the local export directory and .tgz
# archive stem (config_helper), and — with a trailing '_' — the anchored
# managed-object filter for remote retention (s3_archiver). Single definition so
# local naming and remote retention can never drift apart: retention only deletes
# objects whose name it recognizes as tool-created.
EXPORT_BASENAME = "bookstack_export"

# pylint: disable=too-many-instance-attributes
class HttpHelper:
    """
    HttpHelper provides an http request helper with config stored and retries built in

    Args:
        :headers: <Dict[str, str]> = all headers to use for http requests
        :config: <HttpConfig> = Configuration with user inputs for http requests

    Returns:
        :HttpHelper: instance with methods to help with http requests.
    """
    def __init__(self, headers: dict[str, str],
                 config: HttpConfig, export_workers: int = 1):
        self.backoff_factor = config.backoff_factor
        self.retry_codes = config.retry_codes
        self.retry_count = config.retry_count
        self.http_timeout = config.timeout
        self.verify_ssl = config.verify_ssl
        # Size the urllib3 connection pool so export_workers concurrent GETs do
        # not exhaust it. Floor at requests' own default (DEFAULT_POOLSIZE) so a low
        # worker count never shrinks the pool below stock behavior; we track that
        # default rather than hardcode it. Single host, so only pool_maxsize matters;
        # pool_connections default is fine.
        # Thread-safety note: when export_workers > 1 this one Session is shared by
        # every worker thread (see archiver._export_nodes_parallel). requests.Session
        # is not contractually thread-safe, but it is safe HERE: the underlying
        # urllib3 connection pool is thread-safe, we never mutate the Session per
        # request (headers are passed per-call), and cookies are blocked in
        # _build_session — so there is no shared mutable per-request state to race.
        self._pool_maxsize = max(DEFAULT_POOLSIZE, export_workers)
        if not self.verify_ssl:
            urllib3.disable_warnings()
        self._headers = headers
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        """build a requests Session with retry adapters mounted for http and https"""
        session = requests.Session()
        # API token auth is stateless: block all cookies so the reused Session never
        # stores and echoes BookStack's `bookstack_session` cookie back on later requests.
        # Sending the server its own session cookie alongside the token makes BookStack
        # return intermittent 403s ("owner of the used API token does not have permission")
        # mid-export. A fresh requests call (pre-Session) never persisted the cookie, so
        # this regressed when the shared Session was introduced.
        session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        # {backoff factor} * (2 ** ({number of previous retries}))
        # {raise_on_status} if status falls in status_forcelist range
        #  and retries have been exhausted.
        # {status_force_list} 413, 429, 503 defaults are overwritten with additional ones
        retries = Retry(total=self.retry_count,
                        backoff_factor=self.backoff_factor,
                        raise_on_status=True,
                        status_forcelist=self.retry_codes)
        adapter = HTTPAdapter(max_retries=retries, pool_maxsize=self._pool_maxsize)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # more details on options: https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html
    def http_get_request(self, url: str) -> requests.Response:
        """make http requests and return response object"""
        try:
            response = self._session.get(url, headers=self._headers,
                                         verify=self.verify_ssl, timeout=self.http_timeout)
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

    def http_get_all(self, url: str, count: int = 500) -> list[dict]:
        """fetch all items from a paginated bookstack list endpoint"""
        parsed = urlparse(url)
        base_query = [(k, v) for k, v in parse_qsl(parsed.query)
                      if k not in ('count', 'offset')]
        all_data: list[dict] = []
        offset = 0
        while True:
            query = urlencode(base_query + [('count', count), ('offset', offset)])
            paginated_url = urlunparse(parsed._replace(query=query))
            body = self.http_get_request(paginated_url).json()
            batch = body.get('data', [])
            if not batch:
                break
            all_data.extend(batch)
            if len(all_data) >= body.get('total', 0):
                break
            offset += count
        return all_data

def oldest_beyond_keep(items: list[T], key, keep_last: int) -> list[T]:
    """Return the oldest items exceeding keep_last (sorted ascending by key).
    Empty if none exceed."""
    ordered = sorted(items, key=key)
    to_delete = len(ordered) - keep_last
    if to_delete <= 0:
        return []
    return ordered[:to_delete]


def check_var(env_key: str, default_val: str, required: bool = True) -> str:
    """
    :param env_key: environment variable to check (takes precedence)
    :param default_val: fallback value if the env var is unset
    :param required: if True, raise when both env var and default are empty

    :return: env var value if set, else default_val
    :raises ValueError: if required and both env var and default_val are empty
    """
    env_value = os.environ.get(env_key, "")
    if env_value:
        log.debug("env key: %s specified; overrides configuration file value if set.", env_key)
        return env_value
    if required and not default_val:
        raise ValueError(
            f"{env_key} is not specified in env and is missing from configuration "
            "- at least one should be set"
        )
    return default_val


def seconds_until_next_cron(schedule: str, now: datetime) -> float:
    """Seconds from `now` until the next time `schedule` (cron expr) fires.

    Accepts standard 5-field cron; croniter also tolerates 6/7-field extended forms.

    `now` is naive/container-local; the result is always strictly positive
    (croniter returns the next future tick), so a cycle that overran its slot
    waits for the next clock match rather than firing immediately.
    """
    return (croniter(schedule, now).get_next(datetime) - now).total_seconds()


def resolve_env_json(env_key: str, target: type[T], default_val: T) -> T:
    """Env-over-file for a JSON env var, parsed AND validated into `target`.

    The env value is a JSON string; parse+validate it here so callers never
    re-read os.environ (that double-probe was the empty-env TypeError bug) and so
    env input gets the same type checking as the YAML-parsed config field. A
    plain json.loads left the env path unvalidated: the resolved value lands on a
    plain attribute that pydantic never re-checks, so APPRISE_URLS='"foo"' would
    hand a bare str to apprise. TypeAdapter rejects wrong shape/element types. A
    set-but-empty env var falls back to default_val.

    :param env_key: environment variable to check (takes precedence)
    :param target: type to validate into, e.g. list[str]
    :param default_val: fallback if the env var is unset/empty
    :return: validated env value if env var set, else default_val
    :raises pydantic.ValidationError: if the env var is set but not valid `target`
    """
    raw = os.environ.get(env_key, "")
    if raw:
        try:
            return TypeAdapter(target).validate_json(raw)
        except ValidationError:
            # pydantic's message names the target type, not the env var; log the
            # env-var name so operators know which value to fix.
            log.error("env var %s did not validate as %s", env_key, target)
            raise
    return default_val
