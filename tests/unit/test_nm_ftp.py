"""Anonymous FTP transport: MDTM is recorded, never promoted to a vintage (SB-01 §1.2, DIR-2)."""

from __future__ import annotations

import ftplib
import hashlib
import inspect
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from glasswell.lineage import ftp as ftp_module
from glasswell.lineage.ftp import (
    FtpHostUnresolved,
    FtpPathMissing,
    download_ftp,
    ftp_url,
    parse_mdtm,
    remote_path_from_url,
)

HOST = "164.64.106.6"
REMOTE = "/Public/OCD/OCD Interface v1.1/core/pool/pool.zip"
PAYLOAD = b"PK\x03\x04" + bytes(range(256)) * 9


class FakeFtp:
    """The four commands the transport issues, in the order it issues them."""

    instances: ClassVar[list[FakeFtp]] = []

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout
        self.calls: list[str] = []
        self.passive: bool | None = None
        self.mdtm_response = "213 20260820002200"
        self.reported_size: int | None = len(PAYLOAD)
        self.payload = PAYLOAD
        self.permission_denied_on = ""
        FakeFtp.instances.append(self)

    def connect(self, host: str, port: int = 21) -> str:
        self.calls.append(f"connect {host}:{port}")
        return "220 ready"

    def login(self, user: str = "", passwd: str = "") -> str:
        self.calls.append(f"login {user} {passwd}")
        return "230 logged in"

    def set_pasv(self, value: bool) -> None:
        self.passive = value

    def voidcmd(self, command: str) -> str:
        self.calls.append(command)
        return f"200 {command}"

    def sendcmd(self, command: str) -> str:
        self.calls.append(command)
        if self.permission_denied_on and command.startswith(self.permission_denied_on):
            raise ftplib.error_perm("550 no such file")
        return self.mdtm_response

    def size(self, path: str) -> int | None:
        self.calls.append(f"SIZE {path}")
        if self.permission_denied_on == "SIZE":
            raise ftplib.error_perm("550 no such file")
        return self.reported_size

    def retrbinary(self, command: str, callback, blocksize: int = 8192) -> str:
        self.calls.append(f"{command} blocksize={blocksize}")
        if self.permission_denied_on == "RETR":
            raise ftplib.error_perm("550 no such file")
        for start in range(0, len(self.payload), blocksize):
            callback(self.payload[start : start + blocksize])
        return "226 transfer complete"

    def quit(self) -> str:
        self.calls.append("QUIT")
        return "221 bye"

    def close(self) -> None:
        self.calls.append("close")


@pytest.fixture
def fake_ftp(monkeypatch: pytest.MonkeyPatch) -> type[FakeFtp]:
    FakeFtp.instances = []
    monkeypatch.setattr(ftp_module, "FTP", FakeFtp)
    return FakeFtp


def test_mdtm_parses_to_utc():
    assert parse_mdtm("213 20260820002200") == datetime(2026, 8, 20, 0, 22, tzinfo=UTC)


def test_mdtm_with_fractional_seconds_still_parses():
    assert parse_mdtm("213 20260820002200.372") == datetime(2026, 8, 20, 0, 22, tzinfo=UTC)


def test_a_malformed_mdtm_is_recorded_and_not_guessed_at():
    assert parse_mdtm("213 not-a-timestamp") is None
    assert parse_mdtm("") is None


def test_the_url_keeps_the_space_in_the_directory_name():
    url = ftp_url(HOST, REMOTE)
    assert url == (
        f"ftp://{HOST}/Public/OCD/OCD%20Interface%20v1.1/core/pool/pool.zip"
    )
    assert remote_path_from_url(url) == (HOST, REMOTE)


def test_the_transport_reads_the_metadata_before_it_reads_the_bytes(fake_ftp, tmp_path: Path):
    destination = tmp_path / "pool.zip"
    download = download_ftp(HOST, REMOTE, destination)

    connection = fake_ftp.instances[0]
    metadata = [index for index, call in enumerate(connection.calls) if call.startswith("MDTM")]
    transfer = [index for index, call in enumerate(connection.calls) if call.startswith("RETR")]
    assert metadata
    assert transfer
    assert metadata[0] < transfer[0]
    assert connection.passive is True
    assert download.mdtm == "213 20260820002200"
    assert download.size_reported == len(PAYLOAD)
    assert download.upstream_mtime == datetime(2026, 8, 20, 0, 22, tzinfo=UTC)


def test_the_bytes_are_hashed_as_they_stream(fake_ftp, tmp_path: Path):
    destination = tmp_path / "pool.zip"
    download = download_ftp(HOST, REMOTE, destination, chunk_bytes=1 << 20)

    assert destination.read_bytes() == PAYLOAD
    assert download.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert download.size_bytes == len(PAYLOAD)
    assert f"RETR {REMOTE} blocksize={1 << 20}" in fake_ftp.instances[0].calls


def test_a_short_transfer_is_a_failure_not_a_truncated_artifact(fake_ftp, tmp_path: Path):
    FakeFtp.instances = []

    class Truncating(FakeFtp):
        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(timeout)
            self.payload = PAYLOAD[:100]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ftp_module, "FTP", Truncating)
        with pytest.raises(OSError, match="truncated"):
            download_ftp(HOST, REMOTE, tmp_path / "pool.zip")


def test_a_connect_failure_halts_rather_than_guessing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    class Unreachable(FakeFtp):
        def connect(self, host: str, port: int = 21) -> str:
            raise OSError("Network is unreachable")

    monkeypatch.setattr(ftp_module, "FTP", Unreachable)
    with pytest.raises(FtpHostUnresolved) as raised:
        download_ftp(HOST, REMOTE, tmp_path / "pool.zip")
    # fetch_raw reads this off the exception, so the ledger says host_unresolved rather than
    # the class name (SB-01 §1.2: halt loudly, re-pin by hand, never scrape).
    assert raised.value.glasswell_reason == "host_unresolved"
    assert isinstance(raised.value, OSError)


def test_a_missing_remote_path_is_its_own_failure(fake_ftp, tmp_path: Path):
    FakeFtp.instances = []

    class Missing(FakeFtp):
        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(timeout)
            self.permission_denied_on = "RETR"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ftp_module, "FTP", Missing)
        with pytest.raises(FtpPathMissing) as raised:
            download_ftp(HOST, REMOTE, tmp_path / "pool.zip")
    assert raised.value.glasswell_reason == "path_missing"


def test_one_session_serves_every_table(fake_ftp, tmp_path: Path):
    """Politeness (SB-01 §1.3): nine artifacts, one connection, sequential."""
    with ftp_module.ftp_session(HOST) as connection:
        for table in ("pool", "ogrid", "property"):
            download_ftp(
                HOST, REMOTE, tmp_path / f"{table}.zip", connection=connection
            )
    assert len(fake_ftp.instances) == 1
    assert fake_ftp.instances[0].calls.count("QUIT") == 1
    assert sum(call.startswith("RETR") for call in fake_ftp.instances[0].calls) == 3


def test_no_code_path_turns_mdtm_into_a_vintage_or_a_source_key():
    """DIR-2: the upstream mtime is evidence about the file, never glasswell's knowledge date."""
    from glasswell.ingest import nm_ocd
    from glasswell.lineage import fetch

    assert not {"vintage", "fetch_vintage", "source_key"} & set(
        ftp_module.FtpDownload.__dataclass_fields__
    )
    for module in (ftp_module, fetch, nm_ocd):
        source = inspect.getsource(module)
        assert re.search(r"(vintage|source_key)\s*=\s*[^\n]*(mdtm|upstream_mtime)", source) is None
