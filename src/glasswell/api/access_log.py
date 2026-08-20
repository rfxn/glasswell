"""Access-log hygiene. uvicorn logs the request line verbatim, so a credential in a query
string lands in journald in cleartext and stays there (B-1). The API refuses a `key` query
parameter outright; this filter is the second line, for anything that reaches the log first.
"""

from __future__ import annotations

import logging
import re

ACCESS_LOGGER = "uvicorn.access"
REDACTED = "key=REDACTED"

_KEY_QUERY_RE = re.compile(r"(?i)\bkey=[^&\s\"']+")


class RedactKeyQuery(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _KEY_QUERY_RE.sub(REDACTED, argument) if isinstance(argument, str) else argument
                for argument in record.args
            )
        if isinstance(record.msg, str):
            record.msg = _KEY_QUERY_RE.sub(REDACTED, record.msg)
        return True


def install_access_log_redaction(logger_name: str = ACCESS_LOGGER) -> None:
    """Idempotent: `create_app()` runs once per process, but a test may call it again."""
    logger = logging.getLogger(logger_name)
    if not any(isinstance(existing, RedactKeyQuery) for existing in logger.filters):
        logger.addFilter(RedactKeyQuery())
