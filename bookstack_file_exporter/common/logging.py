import json
import logging
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
        for key, val in record.__dict__.items():
            if key not in _RESERVED_ATTRS:
                out[key] = val
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            out["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(out, default=str)


_TEXT_FMT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def build_handler(log_format: str) -> logging.StreamHandler:
    """Return a stream handler whose formatter matches `log_format`."""
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FMT, datefmt=_DATE_FMT))
    return handler
