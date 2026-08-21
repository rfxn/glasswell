"""Anonymous FTP transport for the NM OCD host (SB-07 §2.4 `ftp_anon`).

The host is pinned by the caller and is never re-resolved here: SB-01 §1.2 rules that a move
halts loudly and is re-pinned by hand, because the EMNRD page publishes the address as an image
and a scraper would guess. MDTM and SIZE are recorded as evidence about the artifact; the
vintage is glasswell's own stamp (DIR-2).
"""

from __future__ import annotations

import ftplib
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from ftplib import FTP
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

FTP_PORT = 21
FTP_TIMEOUT_SECONDS = 60.0
ANONYMOUS_USER = "anonymous"
# An anonymous password that says who is calling; the source has no published grant, so the
# operator can identify and contact the client that pulled (SB-01 §1.3).
ANONYMOUS_PASSWORD = "glasswell@rfxn.com"
CHUNK_BYTES = 1 << 20


class FtpError(OSError):
    """Base for FTP transport failures. OSError so fetch_raw's handler emits raw.fetch_failed."""

    glasswell_reason = "ftp_error"


class FtpHostUnresolved(FtpError):
    glasswell_reason = "host_unresolved"


class FtpPathMissing(FtpError):
    glasswell_reason = "path_missing"


class FtpTransferFailed(FtpError):
    glasswell_reason = "ftp_transfer_failed"


@dataclass(frozen=True, slots=True)
class FtpDownload:
    path: Path
    sha256: str
    size_bytes: int
    host: str
    remote_path: str
    mdtm: str | None
    size_reported: int | None
    upstream_mtime: datetime | None


def ftp_url(host: str, remote_path: str, *, port: int = FTP_PORT) -> str:
    """The URL recorded on the manifest. `OCD Interface v1.1` carries a space; it is encoded."""
    authority = host if port == FTP_PORT else f"{host}:{port}"
    return f"ftp://{authority}{quote(remote_path)}"


def remote_path_from_url(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.hostname or "", unquote(parts.path)


def parse_mdtm(response: str) -> datetime | None:
    """`213 YYYYMMDDHHMMSS[.fff]` to UTC. A malformed reply is recorded, never guessed at."""
    stamp = response.split()[-1] if response.split() else ""
    stamp = stamp.split(".")[0]
    if len(stamp) != 14 or not stamp.isdigit():
        return None
    try:
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


@contextmanager
def ftp_session(
    host: str,
    *,
    port: int = FTP_PORT,
    timeout: float = FTP_TIMEOUT_SECONDS,
    user: str = ANONYMOUS_USER,
    password: str = ANONYMOUS_PASSWORD,
) -> Iterator[FTP]:
    """One connection for a whole pull: nine artifacts, sequential, one login (SB-01 §1.3)."""
    connection = connect_ftp(host, port=port, timeout=timeout, user=user, password=password)
    try:
        yield connection
    finally:
        close_ftp(connection)


def close_ftp(connection: FTP) -> None:
    try:
        connection.quit()
    except ftplib.all_errors:  # a server that drops the control channel is not a fetch failure
        connection.close()


def connect_ftp(
    host: str,
    *,
    port: int = FTP_PORT,
    timeout: float = FTP_TIMEOUT_SECONDS,
    user: str = ANONYMOUS_USER,
    password: str = ANONYMOUS_PASSWORD,
) -> FTP:
    connection = FTP(timeout=timeout)
    try:
        connection.connect(host, port)
        connection.login(user, password)
    except ftplib.all_errors as error:
        raise FtpHostUnresolved(
            f"{host}:{port} did not answer as an anonymous FTP host: {error}"
        ) from error
    connection.set_pasv(True)
    return connection


def download_ftp(
    host: str,
    remote_path: str,
    destination: Path | str,
    *,
    port: int = FTP_PORT,
    timeout: float = FTP_TIMEOUT_SECONDS,
    connection: FTP | None = None,
    chunk_bytes: int = CHUNK_BYTES,
) -> FtpDownload:
    """Stream one remote file to `destination`, hashing as it lands."""
    target = Path(destination)
    session = connection or connect_ftp(host, port=port, timeout=timeout)
    try:
        mdtm, size_reported = _metadata(session, remote_path)
        digest = hashlib.sha256()
        written = 0
        with target.open("wb") as handle:

            def receive(chunk: bytes) -> None:
                nonlocal written
                digest.update(chunk)
                written += len(chunk)
                handle.write(chunk)

            try:
                session.retrbinary(f"RETR {remote_path}", receive, blocksize=chunk_bytes)
            except ftplib.error_perm as error:
                raise FtpPathMissing(f"{remote_path} could not be retrieved: {error}") from error
            except ftplib.all_errors as error:
                raise FtpTransferFailed(f"{remote_path} transfer failed: {error}") from error
        if size_reported is not None and written != size_reported:
            raise FtpTransferFailed(
                f"{remote_path} truncated: SIZE said {size_reported}, {written} landed"
            )
    finally:
        if connection is None:
            close_ftp(session)

    return FtpDownload(
        path=target,
        sha256=digest.hexdigest(),
        size_bytes=written,
        host=host,
        remote_path=remote_path,
        mdtm=mdtm,
        size_reported=size_reported,
        upstream_mtime=parse_mdtm(mdtm or ""),
    )


def _metadata(session: FTP, remote_path: str) -> tuple[str | None, int | None]:
    """MDTM and SIZE before the transfer, so a failed RETR still leaves the evidence."""
    session.voidcmd("TYPE I")
    try:
        mdtm: str | None = session.sendcmd(f"MDTM {remote_path}")
    except ftplib.error_perm as error:
        raise FtpPathMissing(f"{remote_path} has no MDTM: {error}") from error
    except ftplib.all_errors:  # MDTM is optional in RFC 3659; its absence is not a failure
        mdtm = None
    try:
        size_reported = session.size(remote_path)
    except ftplib.error_perm as error:
        raise FtpPathMissing(f"{remote_path} has no SIZE: {error}") from error
    except ftplib.all_errors:  # same: an unsupported SIZE leaves the field null, not the pull
        size_reported = None
    return mdtm, size_reported
