import os

from bookstack_file_exporter.config_helper.models import S3StorageConfig


## convenience class — one resolved, boto3-ready object storage target
# pylint: disable=too-few-public-methods,too-many-instance-attributes
class S3ProviderConfig:
    """Resolved, boto3-ready view of one S3StorageConfig entry.

    Owns the raw->resolved logic (endpoint scheme, region default, addressing inference,
    credential env lookup), so config_helper just constructs one per entry and the archiver
    consumes flat values. Constructing this reads os.environ for '*_env' credential names and
    may raise ValueError if a referenced var is unset/empty (fail-closed; the pydantic model
    already guarantees some credential source is configured). For a future non-S3 provider,
    a sibling class (e.g. AzureProviderConfig) would own its own resolution — dispatch by
    constructing the right class, no type switch."""
    def __init__(self, entry: S3StorageConfig):
        self.name = entry.name
        self.bucket = entry.bucket
        # normalized: no leading/trailing '/'. A leading '/' would become a literal
        # empty top-level "folder" in object keys; consumers join with '/' themselves.
        self.prefix = (entry.prefix or "").strip("/")
        self.keep_last = entry.keep_last
        self.endpoint_url = self._resolve_endpoint_url(entry)
        self.region = self._resolve_region(entry)
        self.addressing_style = self._resolve_addressing(entry)
        self.access_key, self.secret_key = self._resolve_credentials(entry)

    @staticmethod
    def _resolve_credentials(entry: S3StorageConfig) -> tuple[str | None, str | None]:
        """Static creds, first match wins: per-entry env NAMES -> inline -> (None, None).
        Once BOTH env names are set they are mandatory — a referenced-but-empty var raises,
        no fallthrough to inline. (None, None) means no explicit creds; only valid when
        entry.ambient_auth is True (the model validator guarantees this), signalling the
        boto3 ambient chain."""
        if entry.access_key_env and entry.secret_key_env:
            access = os.environ.get(entry.access_key_env)
            secret = os.environ.get(entry.secret_key_env)
            if not access or not secret:
                raise ValueError(
                    f"credential env vars {entry.access_key_env}/{entry.secret_key_env} "
                    "are referenced but not set or empty")
            return access, secret
        if entry.access_key and entry.secret_key:
            return entry.access_key, entry.secret_key
        return None, None

    @staticmethod
    def _resolve_endpoint_url(entry: S3StorageConfig) -> str | None:
        """boto3 endpoint_url: explicit endpoint -> scheme://endpoint (scheme from `secure`);
        no endpoint -> None (AWS default regional endpoint, derived from region_name)."""
        if entry.endpoint:
            scheme = "https" if entry.secure else "http"
            return f"{scheme}://{entry.endpoint}"
        return None

    @staticmethod
    def _resolve_region(entry: S3StorageConfig) -> str | None:
        """region_name for boto3. Explicit region wins. Else default us-east-1 when an endpoint
        is set (skips boto3's GetBucketLocation discovery — fragile on compat stores — and
        satisfies SigV4; cosmetic for MinIO/R2/B2). No endpoint + no region -> None (AWS under
        ambient_auth; botocore resolves region from env/profile)."""
        if entry.region:
            return entry.region
        if entry.endpoint:
            return "us-east-1"
        return None

    @staticmethod
    def _resolve_addressing(entry: S3StorageConfig) -> str:
        """botocore addressing_style, passed through verbatim when set. Unset => infer:
        an endpoint (custom store, commonly MinIO/Ceph) -> 'path' (works OOTB; note
        botocore treats 'auto' the same as 'path' whenever endpoint_url is set, so
        'virtual' is the only value that gets virtual-hosted on a custom store);
        no endpoint (AWS) -> 'auto' (virtual-hosted)."""
        if entry.addressing_style:
            return entry.addressing_style
        return "path" if entry.endpoint else "auto"
