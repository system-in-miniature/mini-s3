"""Immutable values for a flat object namespace.

S3 keys are opaque strings. A slash has no storage meaning: ``a/b`` is not a
file named ``b`` inside directory ``a``. Directory-like views are computed by
``list_objects`` from its ``prefix`` and ``delimiter`` arguments.

An object record is an ordered history. Data versions carry a complete byte
body because PUT replaces an object as a whole; delete markers carry no body.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5
from typing import TypeAlias


NULL_VERSION_ID = "null"


def content_etag(body: bytes) -> str:
    """Return S3's quoted hexadecimal MD5 ETag for a non-multipart body."""

    # usedforsecurity=False documents that MD5 is an object fingerprint here,
    # not an authentication or collision-resistance primitive.
    digest = md5(body, usedforsecurity=False).hexdigest()
    return f'"{digest}"'


@dataclass(frozen=True, slots=True)
class Version:
    """One immutable, complete value of an object."""

    version_id: str
    storage_id: str
    sequence: int
    body: bytes
    etag: str
    created_at: float = 0.0
    multipart_upload_id: str | None = None

    @property
    def size(self) -> int:
        """Number of bytes in the complete object value."""

        return len(self.body)

    @property
    def is_delete_marker(self) -> bool:
        """Allow data versions and markers to share listing code."""

        return False


@dataclass(frozen=True, slots=True)
class DeleteMarker:
    """A version whose presence hides older data without deleting it."""

    version_id: str
    storage_id: str
    sequence: int
    created_at: float = 0.0

    @property
    def is_delete_marker(self) -> bool:
        return True


ObjectVersion: TypeAlias = Version | DeleteMarker


@dataclass(frozen=True, slots=True)
class ObjectRecord:
    """All versions for one exact key, newest first."""

    key: str
    versions: tuple[ObjectVersion, ...] = ()
