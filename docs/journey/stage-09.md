# Stage 09 · Multipart domain and validation

### Goal

Model multipart upload identity, staged parts, ordered completion rules, and composite ETags before storage orchestration.

??? note "Deliverable files"
    - `src/minis3/errors.py`
    - `src/minis3/multipart.py`
    - `tests/test_multipart_domain.py`

### The problem at this point

Whole-object PUT cannot represent a client uploading large content in independently retryable parts. Completion also cannot trust a list of part numbers alone: order, ETags, existence, and minimum nonfinal size all affect the final object.

### Failure preview

The domain contract supplies staged parts and a client completion manifest. Swapping two entries must raise `InvalidPartOrder`; naming the right part with the wrong ETag must raise `InvalidPart`. Without these checks, completion can silently assemble bytes the client did not authorize.

### Basic concepts

`MultipartUpload` identifies one private staging session. `StagedPart` owns bytes and derives its receipt (`part_number`, ETag, size). The completion manifest is the client's ordered claim about which staged parts should form the object.

A multipart ETag is not the MD5 of assembled bytes. MiniS3 decodes each quoted part MD5 to binary, concatenates those digests, hashes the concatenation, then appends `-N` for the number of parts.

### Why this mechanism is necessary

Validation is a domain rule shared by any future storage adapter. Keeping it pure prevents disk layout and service locking from obscuring errors, and ensures an invalid manifest cannot begin publication.

### Runtime mental model

`validate_completion` normalizes each client entry, enforces strictly increasing part numbers, resolves each staged part, compares ETags, checks every nonfinal part size, then returns the selected parts and composite ETag. It performs no I/O and mutation.

### File-by-file walkthrough

#### `src/minis3/errors.py`

##### What it is and why it appears

The public failure vocabulary gains missing-upload, invalid-part, invalid-order, and too-small-part meanings.

##### Runtime role

Domain validation and later service/storage code raise the same precise types, allowing callers to distinguish retryable identity errors from invalid completion requests.

##### Key code

```python
class EntityTooSmall(MiniS3Error):
```

##### Statement understanding

Part size is not a generic `ValueError`; it is an S3-shaped completion failure with stable meaning at the public boundary.

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

##### What it is and why it appears

This file owns multipart values and the pure completion validator.

##### Runtime role

Storage will persist these values and the service will call the validator, but neither needs to reimplement ordering, receipt, or ETag rules.

##### Key code

```python
return tuple(selected), f'"{composite}-{len(selected)}"'
```

##### Statement understanding

The return keeps validated order and its derived composite fingerprint together. The `-N` suffix records part count and distinguishes multipart ETags from normal whole-body ETags.

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

##### What it is and why it appears

This focused contract makes completion rules visible before durable staging is added.

##### Runtime role

It supplies explicit staged parts and manifests, proving both accepted order/composite ETag and the major rejection paths.

##### Key code

```python
def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
```

##### Statement understanding

The test name captures two independent obligations: client order is semantic, and composite hashing uses binary digests rather than concatenated hexadecimal text.

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

Run `uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`. It proves pure completion validation only; no staged bytes are durable or visible yet.

### Durable takeaways

Multipart has its own identity and receipts; the client chooses an ordered manifest; every nonfinal part obeys size rules; composite ETag is a digest of binary digests.

### Explain it in your own words

Multipart completion is not simple concatenation. MiniS3 first verifies that the client's ordered receipts exactly match durable staged parts and size rules, then derives the composite ETag. Only a validated ordered result may later be published as one object.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-08...stage-09)

After finishing, use `git checkout stage-09` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/09-multipart-domain/stage.patch)
