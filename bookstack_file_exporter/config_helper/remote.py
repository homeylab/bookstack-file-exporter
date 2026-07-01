## convenience class — one resolved, boto3-ready object storage target
# pylint: disable=too-few-public-methods,too-many-instance-attributes
class S3ProviderConfig:
    """Resolved, boto3-ready configuration for a single object storage target.

    Self-contained: carries both the resolved boto3 connection params AND the target's
    identity/retention fields, so the archiver consumes one flat object and never reaches
    back into the raw pydantic config.

    Args:
        name <str> = unique target identity (used in logs/notifications).
        bucket <str> = destination bucket.
        prefix <str|None> = object-key prefix (raw; the archiver normalizes trailing slashes).
        keep_last <int|None> = retention count (0/None => keep all; negative => no prune).
        endpoint_url <str|None> = full URL (scheme://host[:port]); None => AWS default endpoint.
        region <str|None> = region_name for boto3 (None => let botocore resolve, ambient only).
        addressing_style <str> = 'path' or 'auto', passed to botocore Config.
        access_key/secret_key <str|None> = explicit static creds; None => botocore ambient chain.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, name: str, bucket: str, prefix: str | None, keep_last: int | None,
                 endpoint_url: str | None, region: str | None, addressing_style: str,
                 access_key: str | None, secret_key: str | None):
        self.name = name
        self.bucket = bucket
        self.prefix = prefix
        self.keep_last = keep_last
        self.endpoint_url = endpoint_url
        self.region = region
        self.addressing_style = addressing_style
        self.access_key = access_key
        self.secret_key = secret_key
