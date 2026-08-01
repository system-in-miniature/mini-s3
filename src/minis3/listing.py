"""Version-history projection over MiniS3 records."""


from __future__ import annotations


from dataclasses import dataclass


from .model import ObjectRecord, Version


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
