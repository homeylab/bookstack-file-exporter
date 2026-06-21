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
        out = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        for key, val in record.__dict__.items():
            if key not in _RESERVED_ATTRS:
                out[key] = val
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)
