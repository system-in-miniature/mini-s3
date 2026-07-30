"""Strongly consistent projections over MiniS3's flat key map.

``delimiter`` does not traverse directories. It partitions matching strings:
the first delimiter after ``prefix`` turns the matching key into a
``common_prefix``; otherwise the key is returned as content. This projection
is the entire "directory illusion."
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
import json

from .errors import InvalidContinuationToken
from .model import DeleteMarker, ObjectRecord, Version


@dataclass(frozen=True, slots=True)
class ListedObject:
    """Current visible metadata for one exact key."""

    key: str
    etag: str
    size: int
    version_id: str


@dataclass(frozen=True, slots=True)
class ListObjectsResult:
    """One page of current objects and derived common prefixes."""

    contents: tuple[ListedObject, ...]
    common_prefixes: tuple[str, ...]
    key_count: int
    next_token: str | None

    @property
    def is_truncated(self) -> bool:
        return self.next_token is not None


@dataclass(frozen=True, slots=True)
class ListedVersion:
    """One data version or delete marker in a flattened history."""

    key: str
    version_id: str
    is_latest: bool
    is_delete_marker: bool
    etag: str | None
    size: int | None


@dataclass(frozen=True, slots=True)
class ListObjectVersionsResult:
    """All retained versions and markers, ordered by key then newest first."""

    versions: tuple[ListedVersion, ...]


def _encode_token(offset: int, prefix: str, delimiter: str | None) -> str:
    payload = json.dumps(
        {"o": offset, "p": prefix, "d": delimiter},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_token(token: str, prefix: str, delimiter: str | None) -> int:
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(urlsafe_b64decode(padded).decode())
        if payload != {"o": payload["o"], "p": prefix, "d": delimiter}:
            raise ValueError
        offset = payload["o"]
        if not isinstance(offset, int) or offset < 0:
            raise ValueError
        return offset
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidContinuationToken(token) from exc


def list_objects(
    records: dict[str, ObjectRecord],
    *,
    prefix: str = "",
    delimiter: str | None = None,
    max_keys: int = 1000,
    continuation_token: str | None = None,
) -> ListObjectsResult:
    """Build one deterministic page from a single in-memory snapshot."""

    if max_keys < 0:
        raise ValueError("max_keys must be non-negative")
    if delimiter == "":
        raise ValueError("delimiter must be non-empty")

    contents: dict[str, ListedObject] = {}
    prefixes: set[str] = set()
    for key, record in records.items():
        if not key.startswith(prefix) or not record.versions:
            continue
        current = record.versions[0]
        if isinstance(current, DeleteMarker):
            continue
        suffix = key[len(prefix) :]
        if delimiter is not None and delimiter in suffix:
            boundary = suffix.index(delimiter) + len(delimiter)
            prefixes.add(prefix + suffix[:boundary])
        else:
            contents[key] = ListedObject(
                key, current.etag, current.size, current.version_id
            )

    combined: list[tuple[str, str]] = [
        *((key, "content") for key in contents),
        *((item, "prefix") for item in prefixes),
    ]
    combined.sort()
    offset = (
        0
        if continuation_token is None
        else _decode_token(continuation_token, prefix, delimiter)
    )
    page = combined[offset : offset + max_keys]
    next_offset = offset + len(page)
    next_token = (
        _encode_token(next_offset, prefix, delimiter)
        if next_offset < len(combined)
        else None
    )
    return ListObjectsResult(
        contents=tuple(contents[key] for key, kind in page if kind == "content"),
        common_prefixes=tuple(key for key, kind in page if kind == "prefix"),
        key_count=len(page),
        next_token=next_token,
    )


def list_object_versions(
    records: dict[str, ObjectRecord],
    *,
    prefix: str = "",
) -> ListObjectVersionsResult:
    """Flatten complete histories without hiding delete markers."""

    result: list[ListedVersion] = []
    for key in sorted(records):
        if not key.startswith(prefix):
            continue
        for index, item in enumerate(records[key].versions):
            is_data = isinstance(item, Version)
            result.append(
                ListedVersion(
                    key=key,
                    version_id=item.version_id,
                    is_latest=index == 0,
                    is_delete_marker=not is_data,
                    etag=item.etag if is_data else None,
                    size=item.size if is_data else None,
                )
            )
    return ListObjectVersionsResult(tuple(result))

