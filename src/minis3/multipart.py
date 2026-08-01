"""Multipart values and completion validation.

An upload part cannot know whether it will be the final part in the eventual
completion list. Therefore the S3 minimum-size rule is intentionally checked
at completion, against every listed part except the last one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import md5

from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder
from .model import content_etag


MIN_PART_SIZE = 5 * 1024 * 1024
MAX_PART_NUMBER = 10_000


@dataclass(frozen=True, slots=True)
class MultipartUpload:
    """Identity of one durable but object-invisible upload."""

    bucket: str
    key: str
    upload_id: str
    sequence: int
    initiated_at: float


@dataclass(frozen=True, slots=True)
class MultipartPart:
    """Public receipt returned after one part has been durably staged."""

    part_number: int
    etag: str
    size: int


@dataclass(frozen=True, slots=True)
class StagedPart:
    """Bytes recovered from an upload's private staging directory."""

    part_number: int
    body: bytes

    @property
    def etag(self) -> str:
        return content_etag(self.body)

    @property
    def size(self) -> int:
        return len(self.body)

    @property
    def receipt(self) -> MultipartPart:
        return MultipartPart(self.part_number, self.etag, self.size)


CompletionEntry = MultipartPart | tuple[int, str]


def _entry_identity(entry: CompletionEntry) -> tuple[int, str]:
    if isinstance(entry, MultipartPart):
        return entry.part_number, entry.etag
    try:
        part_number, etag = entry
    except (TypeError, ValueError) as exc:
        raise InvalidPart(entry) from exc
    if not isinstance(part_number, int) or not isinstance(etag, str):
        raise InvalidPart(entry)
    return part_number, etag


def validate_completion(
    staged: dict[int, StagedPart],
    entries: Sequence[CompletionEntry],
    *,
    minimum_part_size: int,
) -> tuple[tuple[StagedPart, ...], str]:
    """Validate a client manifest and return ordered parts plus composite ETag."""

    identities = tuple(_entry_identity(entry) for entry in entries)
    if not identities:
        raise InvalidPart("completion list must contain at least one part")
    numbers = tuple(part_number for part_number, _etag in identities)
    if any(left >= right for left, right in zip(numbers, numbers[1:])):
        raise InvalidPartOrder(numbers)

    selected: list[StagedPart] = []
    for part_number, expected_etag in identities:
        part = staged.get(part_number)
        if part is None or part.etag != expected_etag:
            raise InvalidPart(f"part {part_number}")
        selected.append(part)
    for part in selected[:-1]:
        if part.size < minimum_part_size:
            raise EntityTooSmall(f"part {part.part_number}")

    # Multipart ETags hash binary MD5 digests, not their hexadecimal strings.
    digests = b"".join(
        md5(part.body, usedforsecurity=False).digest() for part in selected
    )
    composite = md5(digests, usedforsecurity=False).hexdigest()
    return tuple(selected), f'"{composite}-{len(selected)}"'
