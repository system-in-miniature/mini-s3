# Stage 02 · Bucket state and deterministic IDs

### Goal

Introduce the bucket aggregate, legal versioning transitions, and an injectable monotonic sequence.

### Deliverable files / 交付文件

- `src/minis3/bucket.py`
- `tests/test_bucket.py`

### Mechanism walkthrough

#### Ownership and flow

`Bucket` owns per-key history and legal versioning transitions. An injected `SequenceCounter` turns each PUT or marker into deterministic public and internal identities.

#### Failure and debugging

Inspect the bucket state before the branch, then compare `version_id`, `storage_id`, and record order after it. Illegal transitions should fail before mutating state.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `src/minis3/bucket.py`

Aggregate that owns per-bucket state transitions.

Called by `MiniS3`; turns one command plus the current record into the next in-memory history.

**Changed anchors:** `VersioningState`, `SequenceCounter`, `__init__`, `__call__`, `ensure_at_least`, `Bucket`, `set_versioning`, `put`, `get`, `delete`

??? note "File diff: src/minis3/bucket.py"
    ```diff
    diff --git a/src/minis3/bucket.py b/src/minis3/bucket.py
    new file mode 100644
    index 0000000..b0a46e5
    --- /dev/null
    +++ b/src/minis3/bucket.py
    @@ -0,0 +1,159 @@
    +"""Bucket ownership and the versioning state machine.
    +
    +The important distinction is between the public version id and an internal
    +storage id. A suspended bucket repeatedly writes public version ``"null"``,
    +but every write still receives a unique storage id so durable publication can
    +refer to immutable files.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable
    +from dataclasses import dataclass, field
    +from enum import StrEnum
    +
    +from .errors import NoSuchKey, NoSuchVersion
    +from .model import (
    +    NULL_VERSION_ID,
    +    DeleteMarker,
    +    ObjectRecord,
    +    ObjectVersion,
    +    Version,
    +    content_etag,
    +)
    +
    +
    +class VersioningState(StrEnum):
    +    """The three bucket versioning states visible in M1."""
    +
    +    UNVERSIONED = "unversioned"
    +    ENABLED = "enabled"
    +    SUSPENDED = "suspended"
    +
    +
    +class SequenceCounter:
    +    """Injectable deterministic sequence source; random ids are forbidden."""
    +
    +    def __init__(self, start: int = 1) -> None:
    +        if start < 1:
    +            raise ValueError("counter start must be positive")
    +        self._next_value = start
    +
    +    def __call__(self) -> int:
    +        value = self._next_value
    +        self._next_value += 1
    +        return value
    +
    +    def ensure_at_least(self, value: int) -> None:
    +        """Advance a default counter beyond sequences recovered from disk."""
    +
    +        self._next_value = max(self._next_value, value)
    +
    +
    +@dataclass(slots=True)
    +class Bucket:
    +    """Mutable aggregate for one bucket; persistence is coordinated by Store."""
    +
    +    name: str
    +    versioning: VersioningState = VersioningState.UNVERSIONED
    +    records: dict[str, ObjectRecord] = field(default_factory=dict)
    +
    +    def set_versioning(self, state: VersioningState | str) -> None:
    +        state = VersioningState(state)
    +        if state is VersioningState.UNVERSIONED and self.versioning is not state:
    +            raise ValueError("versioning cannot return to unversioned after it is enabled")
    +        if (
    +            self.versioning is VersioningState.UNVERSIONED
    +            and state is VersioningState.SUSPENDED
    +        ):
    +            raise ValueError("versioning must be enabled before it can be suspended")
    +        self.versioning = state
    +
    +    def put(self, key: str, body: bytes, next_sequence: Callable[[], int]) -> Version:
    +        sequence = next_sequence()
    +        version_id = (
    +            f"v{sequence:08d}"
    +            if self.versioning is VersioningState.ENABLED
    +            else NULL_VERSION_ID
    +        )
    +        version = Version(
    +            version_id=version_id,
    +            storage_id=f"e{sequence:08d}",
    +            sequence=sequence,
    +            body=bytes(body),
    +            etag=content_etag(body),
    +        )
    +        old = self.records.get(key, ObjectRecord(key))
    +
    +        if self.versioning is VersioningState.ENABLED:
    +            versions = (version, *old.versions)
    +        else:
    +            # Unversioned and suspended writes replace only the null slot. In
    +            # suspended state, named historical versions remain reachable.
    +            retained = tuple(
    +                item for item in old.versions if item.version_id != NULL_VERSION_ID
    +            )
    +            versions = (version, *retained)
    +        self.records[key] = ObjectRecord(key, versions)
    +        return version
    +
    +    def get(self, key: str, version_id: str | None = None) -> Version:
    +        record = self.records.get(key)
    +        if record is None or not record.versions:
    +            raise NoSuchKey(key)
    +
    +        if version_id is None:
    +            candidate = record.versions[0]
    +            if isinstance(candidate, DeleteMarker):
    +                raise NoSuchKey(key)
    +            return candidate
    +
    +        for candidate in record.versions:
    +            if candidate.version_id == version_id:
    +                if isinstance(candidate, DeleteMarker):
    +                    raise NoSuchKey(key)
    +                return candidate
    +        raise NoSuchVersion(f"{key}:{version_id}")
    +
    +    def delete(
    +        self,
    +        key: str,
    +        next_sequence: Callable[[], int],
    +        version_id: str | None = None,
    +    ) -> ObjectVersion | None:
    +        record = self.records.get(key)
    +
    +        if version_id is not None:
    +            if record is None:
    +                raise NoSuchVersion(f"{key}:{version_id}")
    +            for index, candidate in enumerate(record.versions):
    +                if candidate.version_id == version_id:
    +                    remaining = record.versions[:index] + record.versions[index + 1 :]
    +                    if remaining:
    +                        self.records[key] = ObjectRecord(key, remaining)
    +                    else:
    +                        self.records.pop(key)
    +                    return candidate
    +            raise NoSuchVersion(f"{key}:{version_id}")
    +
    +        has_named_history = record is not None and any(
    +            item.version_id != NULL_VERSION_ID for item in record.versions
    +        )
    +        if self.versioning is VersioningState.UNVERSIONED and not has_named_history:
    +            self.records.pop(key, None)
    +            return None
    +
    +        sequence = next_sequence()
    +        marker_id = (
    +            f"v{sequence:08d}"
    +            if self.versioning is VersioningState.ENABLED
    +            else NULL_VERSION_ID
    +        )
    +        marker = DeleteMarker(marker_id, f"e{sequence:08d}", sequence)
    +        old_versions = () if record is None else record.versions
    +        if self.versioning is VersioningState.SUSPENDED or has_named_history:
    +            old_versions = tuple(
    +                item for item in old_versions if item.version_id != NULL_VERSION_ID
    +            )
    +        self.records[key] = ObjectRecord(key, (marker, *old_versions))
    +        return marker
    ```

#### `tests/test_bucket.py`

Executable proof of the stage behavior.

Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

**Changed anchors:** `test_bucket_owns_versioning_transitions_and_deterministic_ids`

??? note "File diff: tests/test_bucket.py"
    ```diff
    diff --git a/tests/test_bucket.py b/tests/test_bucket.py
    new file mode 100644
    index 0000000..139fcf0
    --- /dev/null
    +++ b/tests/test_bucket.py
    @@ -0,0 +1,21 @@
    +"""Focused contracts for the bucket aggregate before service wiring."""
    +
    +import pytest
    +
    +from minis3.bucket import Bucket, SequenceCounter, VersioningState
    +
    +
    +def test_bucket_owns_versioning_transitions_and_deterministic_ids() -> None:
    +    bucket = Bucket("b")
    +    counter = SequenceCounter()
    +
    +    null = bucket.put("key", b"before", counter)
    +    bucket.set_versioning(VersioningState.ENABLED)
    +    named = bucket.put("key", b"after", counter)
    +    bucket.set_versioning(VersioningState.SUSPENDED)
    +
    +    assert (null.version_id, null.storage_id) == ("null", "e00000001")
    +    assert (named.version_id, named.storage_id) == ("v00000002", "e00000002")
    +    assert bucket.get("key").body == b"after"
    +    with pytest.raises(ValueError):
    +        bucket.set_versioning(VersioningState.UNVERSIONED)
    ```

### Verification evidence

`uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`

This stage adds 1 executable case(s), anchored at `test_bucket_owns_versioning_transitions_and_deterministic_ids`. Run them after the mechanism walkthrough; the cumulative gate also reruns every earlier stage contract.

### Concept check

Which invariant must remain true after this stage?

??? note "Answer"
    Versioning can be enabled and suspended, but never reset to the never-enabled state.

### Code-reading check

Start at `VersioningState` in `src/minis3/bucket.py`: what state or value enters this boundary, and which owner consumes the result next?

??? note "Answer"
    Called by `MiniS3`; turns one command plus the current record into the next in-memory history.

### Interview-ready summary

Versioning can be enabled and suspended, but never reset to the never-enabled state.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-01...stage-02)

After finishing, use `git checkout stage-02` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/02-bucket-state/stage.patch)
