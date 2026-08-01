"""Crash-safe file publication shared across the System-in-Miniature series.

The recurring pattern is: write a temporary file, flush its bytes with fsync,
rename it atomically into place, then fsync the parent directory. Readers only
open the final name, so they observe the old complete file or the new complete
file, never a partially written file.
"""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path


class InjectedCrash(RuntimeError):
    """A deliberate process-crash boundary used by tests and labs."""


CrashInjector = Callable[[str], None]


def fsync_directory(path: Path) -> None:
    """Persist directory-entry changes on POSIX filesystems."""

    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_mkdir(path: Path, *, parents: bool = True) -> None:
    """Create directories and persist every new entry in its parent."""

    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent

    path.mkdir(parents=parents, exist_ok=True)
    for created in reversed(missing):
        fsync_directory(created.parent)


def atomic_write(path: Path, payload: bytes) -> None:
    """Publish one complete file using the series-wide crash-safe pattern."""

    durable_mkdir(path.parent)
    temporary = path.with_name(path.name + ".tmp-write")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)
