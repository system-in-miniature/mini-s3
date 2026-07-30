"""Bucket ownership and the versioning state machine.

The important distinction is between the public version id and an internal
storage id. A suspended bucket repeatedly writes public version ``"null"``,
but every write still receives a unique storage id so durable publication can
refer to immutable files.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from .errors import NoSuchKey, NoSuchVersion
from .model import (
    NULL_VERSION_ID,
    DeleteMarker,
    ObjectRecord,
    ObjectVersion,
    Version,
    content_etag,
)


class VersioningState(StrEnum):
    """The three bucket versioning states visible in M1."""

    UNVERSIONED = "unversioned"
    ENABLED = "enabled"
    SUSPENDED = "suspended"


class SequenceCounter:
    """Injectable deterministic sequence source; random ids are forbidden."""

    def __init__(self, start: int = 1) -> None:
        if start < 1:
            raise ValueError("counter start must be positive")
        self._next_value = start

    def __call__(self) -> int:
        value = self._next_value
        self._next_value += 1
        return value

    def ensure_at_least(self, value: int) -> None:
        """Advance a default counter beyond sequences recovered from disk."""

        self._next_value = max(self._next_value, value)


@dataclass(slots=True)
class Bucket:
    """Mutable aggregate for one bucket; persistence is coordinated by Store."""

    name: str
    versioning: VersioningState = VersioningState.UNVERSIONED
    records: dict[str, ObjectRecord] = field(default_factory=dict)

    def set_versioning(self, state: VersioningState | str) -> None:
        state = VersioningState(state)
        if self.versioning is VersioningState.UNVERSIONED and state is VersioningState.SUSPENDED:
            raise ValueError("versioning must be enabled before it can be suspended")
        self.versioning = state

    def put(self, key: str, body: bytes, next_sequence: Callable[[], int]) -> Version:
        sequence = next_sequence()
        version_id = (
            f"v{sequence:08d}"
            if self.versioning is VersioningState.ENABLED
            else NULL_VERSION_ID
        )
        version = Version(
            version_id=version_id,
            storage_id=f"e{sequence:08d}",
            sequence=sequence,
            body=bytes(body),
            etag=content_etag(body),
        )
        old = self.records.get(key, ObjectRecord(key))

        if self.versioning is VersioningState.ENABLED:
            versions = (version, *old.versions)
        else:
            # Unversioned and suspended writes replace only the null slot. In
            # suspended state, named historical versions remain reachable.
            retained = tuple(
                item for item in old.versions if item.version_id != NULL_VERSION_ID
            )
            versions = (version, *retained)
        self.records[key] = ObjectRecord(key, versions)
        return version

    def get(self, key: str, version_id: str | None = None) -> Version:
        record = self.records.get(key)
        if record is None or not record.versions:
            raise NoSuchKey(key)

        if version_id is None:
            candidate = record.versions[0]
            if isinstance(candidate, DeleteMarker):
                raise NoSuchKey(key)
            return candidate

        for candidate in record.versions:
            if candidate.version_id == version_id:
                if isinstance(candidate, DeleteMarker):
                    raise NoSuchKey(key)
                return candidate
        raise NoSuchVersion(f"{key}:{version_id}")

    def delete(
        self,
        key: str,
        next_sequence: Callable[[], int],
        version_id: str | None = None,
    ) -> ObjectVersion | None:
        record = self.records.get(key)

        if version_id is not None:
            if record is None:
                raise NoSuchVersion(f"{key}:{version_id}")
            for index, candidate in enumerate(record.versions):
                if candidate.version_id == version_id:
                    remaining = record.versions[:index] + record.versions[index + 1 :]
                    if remaining:
                        self.records[key] = ObjectRecord(key, remaining)
                    else:
                        self.records.pop(key)
                    return candidate
            raise NoSuchVersion(f"{key}:{version_id}")

        if self.versioning is VersioningState.UNVERSIONED:
            self.records.pop(key, None)
            return None

        sequence = next_sequence()
        marker_id = (
            f"v{sequence:08d}"
            if self.versioning is VersioningState.ENABLED
            else NULL_VERSION_ID
        )
        marker = DeleteMarker(marker_id, f"e{sequence:08d}", sequence)
        old_versions = () if record is None else record.versions
        if self.versioning is VersioningState.SUSPENDED:
            old_versions = tuple(
                item for item in old_versions if item.version_id != NULL_VERSION_ID
            )
        self.records[key] = ObjectRecord(key, (marker, *old_versions))
        return marker

