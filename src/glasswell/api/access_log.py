"""Access-log hygiene. uvicorn logs the request line verbatim, so a credential in a query
string lands in journald in cleartext and stays there (B-1). The API refuses a `key` query
parameter outright; this filter is the second line, for anything that reaches the log first.
"""

from __future__ import annotations

import logging
import re

ACCESS_LOGGER = "uvicorn.access"
REDACTED = "REDACTED"

# Every credential-shaped query parameter, not just `key`. The API refuses three of these
# outright; this is the second line, for anything that reaches the log first.
_CREDENTIAL_QUERY_RE = re.compile(r"(?i)\b(key|password|token|session|csrf)=[^&\s\"']+")
# A session token anywhere in a record, not only in a query string -- a stray repr() of a
# cookie header would otherwise put a live credential in journald.
_SESSION_TOKEN_RE = re.compile(r"gws_[A-Za-z0-9_-]{20,}")


def redact(text: str) -> str:
    text = _CREDENTIAL_QUERY_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    return _SESSION_TOKEN_RE.sub(f"gws_{REDACTED}", text)


class RedactKeyQuery(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact(argument) if isinstance(argument, str) else argument
                for argument in record.args
            )
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        return True


def install_access_log_redaction(logger_name: str = ACCESS_LOGGER) -> None:
    """Idempotent: `create_app()` runs once per process, but a test may call it again."""
    logger = logging.getLogger(logger_name)
    if not any(isinstance(existing, RedactKeyQuery) for existing in logger.filters):
        logger.addFilter(RedactKeyQuery())
