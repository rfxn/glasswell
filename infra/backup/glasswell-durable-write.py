#!/usr/bin/python3
"""Publish a JSON receipt to an absolute path atomically, refusing an unsafe target.

Reads the payload on stdin and replaces the target in one rename, so a reader never observes a
half-written proof. The target-safety checks are the point: a receipt is read by a less
privileged process than the one that writes it, so the writer must refuse a path that a symlink,
a hard link or a mode change could have turned into someone else's file.
"""

from __future__ import annotations

import contextlib
import grp
import json
import os
import pwd
import stat
import sys
import tempfile
from pathlib import Path

MODE = 0o640


def resolve_identity(value: str, lookup) -> int:
    return int(value) if value.isdecimal() else lookup(value)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        raise SystemExit("usage: glasswell-durable-write.py <target> <uid> <gid>")
    target = Path(argv[1])
    if not target.is_absolute():
        raise SystemExit("receipt path must be absolute")

    parent = target.parent
    parent_metadata = parent.lstat()
    if not stat.S_ISDIR(parent_metadata.st_mode) or parent.is_symlink():
        raise SystemExit("receipt parent is unsafe")
    if parent.resolve(strict=True) != parent:
        raise SystemExit("receipt parent has a symlink component")

    uid = resolve_identity(argv[2], lambda name: pwd.getpwnam(name).pw_uid)
    gid = resolve_identity(argv[3], lambda name: grp.getgrnam(name).gr_gid)

    try:
        existing = target.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if not stat.S_ISREG(existing.st_mode) or target.is_symlink() or existing.st_nlink != 1:
            raise SystemExit("receipt target is unsafe")
        if (existing.st_uid, existing.st_gid, stat.S_IMODE(existing.st_mode)) != (uid, gid, MODE):
            raise SystemExit("receipt target ownership or mode is unsafe")

    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise SystemExit("receipt payload must be a JSON object")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, MODE)
        os.fchown(descriptor, uid, gid)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
