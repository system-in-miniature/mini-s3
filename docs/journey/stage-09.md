# Stage 09 · Multipart domain and validation

### Goal

Model upload identity, staged parts, completion manifests, size rules, and composite ETags.

### Deliverable files / 交付文件

- `src/minis3/errors.py`
- `src/minis3/multipart.py`
- `tests/test_multipart_domain.py`

### Mechanism walkthrough

#### Ownership and flow

`multipart.py` owns upload/part values and pure completion validation: client entries select staged parts, enforce ordering and size rules, then produce a composite ETag.

#### Failure and debugging

Compare client identities with staged receipts before assembly. Wrong order, missing parts, mismatched ETags, and undersized non-final parts must fail independently.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `src/minis3/errors.py`

Shared domain failure vocabulary.

Constructed by bucket/service code and returned upward without owning I/O; inspect field values when state is correct but results look wrong.

**Changed anchors:** `NoSuchUpload`, `InvalidPart`, `InvalidPartOrder`, `EntityTooSmall`

??? note "File diff: src/minis3/errors.py"
    ```diff
    diff --git a/src/minis3/errors.py b/src/minis3/errors.py
    index e1a2230..9db3b4c 100644
    --- a/src/minis3/errors.py
    +++ b/src/minis3/errors.py
    @@ -28,3 +28,18 @@ class NoSuchVersion(MiniS3Error):
     class InvalidContinuationToken(MiniS3Error):
         """The list continuation token was malformed or belongs to another query."""

    +
    +class NoSuchUpload(MiniS3Error):
    +    """The addressed multipart upload does not exist or no longer exists."""
    +
    +
    +class InvalidPart(MiniS3Error):
    +    """A completion entry names a missing part or the wrong part ETag."""
    +
    +
    +class InvalidPartOrder(MiniS3Error):
    +    """Multipart completion entries were not in strictly ascending order."""
    +
    +
    +class EntityTooSmall(MiniS3Error):
    +    """A non-final multipart part is below the configured minimum size."""
    ```

#### `src/minis3/multipart.py`

Multipart values and completion rules.

Called by `MiniS3` as a policy function; receives explicit values and returns a decision for the service to apply.

**Changed anchors:** `MultipartUpload`, `MultipartPart`, `StagedPart`, `etag`, `size`, `receipt`, `_entry_identity`, `validate_completion`

??? note "File diff: src/minis3/multipart.py"
    ```diff
    diff --git a/src/minis3/multipart.py b/src/minis3/multipart.py
    new file mode 100644
    index 0000000..c10ab02
    --- /dev/null
    +++ b/src/minis3/multipart.py
    @@ -0,0 +1,107 @@
    +"""Multipart values and completion validation.
    +
    +An upload part cannot know whether it will be the final part in the eventual
    +completion list. Therefore the S3 minimum-size rule is intentionally checked
    +at completion, against every listed part except the last one.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Sequence
    +from dataclasses import dataclass
    +from hashlib import md5
    +
    +from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder
    +from .model import content_etag
    +
    +
    +MIN_PART_SIZE = 5 * 1024 * 1024
    +MAX_PART_NUMBER = 10_000
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class MultipartUpload:
    +    """Identity of one durable but object-invisible upload."""
    +
    +    bucket: str
    +    key: str
    +    upload_id: str
    +    sequence: int
    +    initiated_at: float
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class MultipartPart:
    +    """Public receipt returned after one part has been durably staged."""
    +
    +    part_number: int
    +    etag: str
    +    size: int
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class StagedPart:
    +    """Bytes recovered from an upload's private staging directory."""
    +
    +    part_number: int
    +    body: bytes
    +
    +    @property
    +    def etag(self) -> str:
    +        return content_etag(self.body)
    +
    +    @property
    +    def size(self) -> int:
    +        return len(self.body)
    +
    +    @property
    +    def receipt(self) -> MultipartPart:
    +        return MultipartPart(self.part_number, self.etag, self.size)
    +
    +
    +CompletionEntry = MultipartPart | tuple[int, str]
    +
    +
    +def _entry_identity(entry: CompletionEntry) -> tuple[int, str]:
    +    if isinstance(entry, MultipartPart):
    +        return entry.part_number, entry.etag
    +    try:
    +        part_number, etag = entry
    +    except (TypeError, ValueError) as exc:
    +        raise InvalidPart(entry) from exc
    +    if not isinstance(part_number, int) or not isinstance(etag, str):
    +        raise InvalidPart(entry)
    +    return part_number, etag
    +
    +
    +def validate_completion(
    +    staged: dict[int, StagedPart],
    +    entries: Sequence[CompletionEntry],
    +    *,
    +    minimum_part_size: int,
    +) -> tuple[tuple[StagedPart, ...], str]:
    +    """Validate a client manifest and return ordered parts plus composite ETag."""
    +
    +    identities = tuple(_entry_identity(entry) for entry in entries)
    +    if not identities:
    +        raise InvalidPart("completion list must contain at least one part")
    +    numbers = tuple(part_number for part_number, _etag in identities)
    +    if any(left >= right for left, right in zip(numbers, numbers[1:])):
    +        raise InvalidPartOrder(numbers)
    +
    +    selected: list[StagedPart] = []
    +    for part_number, expected_etag in identities:
    +        part = staged.get(part_number)
    +        if part is None or part.etag != expected_etag:
    +            raise InvalidPart(f"part {part_number}")
    +        selected.append(part)
    +    for part in selected[:-1]:
    +        if part.size < minimum_part_size:
    +            raise EntityTooSmall(f"part {part.part_number}")
    +
    +    # Multipart ETags hash binary MD5 digests, not their hexadecimal strings.
    +    digests = b"".join(
    +        md5(part.body, usedforsecurity=False).digest() for part in selected
    +    )
    +    composite = md5(digests, usedforsecurity=False).hexdigest()
    +    return tuple(selected), f'"{composite}-{len(selected)}"'
    ```

#### `tests/test_multipart_domain.py`

Executable proof of the stage behavior.

Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

**Changed anchors:** `test_completion_validation_orders_parts_and_hashes_binary_digests`

??? note "File diff: tests/test_multipart_domain.py"
    ```diff
    diff --git a/tests/test_multipart_domain.py b/tests/test_multipart_domain.py
    new file mode 100644
    index 0000000..9b7026a
    --- /dev/null
    +++ b/tests/test_multipart_domain.py
    @@ -0,0 +1,40 @@
    +"""Focused contract for multipart validation before storage orchestration."""
    +
    +from hashlib import md5
    +
    +import pytest
    +
    +from minis3.errors import EntityTooSmall, InvalidPartOrder
    +from minis3.multipart import StagedPart, validate_completion
    +
    +
    +def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
    +    first = StagedPart(1, b"abc")
    +    last = StagedPart(2, b"x")
    +    staged = {1: first, 2: last}
    +
    +    selected, etag = validate_completion(
    +        staged,
    +        [first.receipt, last.receipt],
    +        minimum_part_size=3,
    +    )
    +
    +    binary_digests = b"".join(
    +        md5(part.body, usedforsecurity=False).digest() for part in selected
    +    )
    +    expected = md5(binary_digests, usedforsecurity=False).hexdigest()
    +    assert selected == (first, last)
    +    assert etag == f'"{expected}-2"'
    +
    +    with pytest.raises(InvalidPartOrder):
    +        validate_completion(
    +            staged,
    +            [last.receipt, first.receipt],
    +            minimum_part_size=3,
    +        )
    +    with pytest.raises(EntityTooSmall):
    +        validate_completion(
    +            {1: StagedPart(1, b"a"), 2: last},
    +            [StagedPart(1, b"a").receipt, last.receipt],
    +            minimum_part_size=3,
    +        )
    ```

### Verification evidence

`uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`

This stage adds 1 executable case(s), anchored at `test_completion_validation_orders_parts_and_hashes_binary_digests`. Run them after the mechanism walkthrough; the cumulative gate also reruns every earlier stage contract.

### Concept check

Which invariant must remain true after this stage?

??? note "Answer"
    Minimum size is checked at completion because only then is the final part known.

### Code-reading check

Start at `MultipartUpload` in `src/minis3/multipart.py`: what state or value enters this boundary, and which owner consumes the result next?

??? note "Answer"
    Called by `MiniS3` as a policy function; receives explicit values and returns a decision for the service to apply.

### Interview-ready summary

Minimum size is checked at completion because only then is the final part known.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-08...stage-09)

After finishing, use `git checkout stage-09` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/09-multipart-domain/stage.patch)
