import json
import logging
import time
from datetime import datetime, timezone

# Standard LogRecord attributes; anything else on a record is a user-supplied
# `extra={}` field and gets merged into the JSON output.
_RESERVED_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
})


class JsonFormatter(logging.Formatter):
    """Render each LogRecord as one JSON object (JSON Lines)."""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        out = {
            # millisecond precision so aggregators can order within a second
            "timestamp": f"{ts.strftime('%Y-%m-%dT%H:%M:%S')}.{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        # Fixed schema keys are authoritative: skip any caller extra whose name collides,
        # so extra={'level': ...}/{'logger': ...}/{'timestamp': ...} can never clobber the
        # real record values (mirrors python-json-logger's static-fields precedence).
        for key, val in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key not in out:
                out[key] = val
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            out["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(out, default=str)


_TEXT_FMT = "%(asctime)s UTC [%(levelname)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def build_handler(log_format: str) -> logging.StreamHandler:
    """Return a stream handler whose formatter matches `log_format`."""
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        formatter = logging.Formatter(_TEXT_FMT, datefmt=_DATE_FMT)
        # %(asctime)s renders via time.localtime by default; pin to UTC so the
        # text format shares one clock with every other surface (JSON logs,
        # health endpoint, notification bodies, archive filenames).
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
    return handler
