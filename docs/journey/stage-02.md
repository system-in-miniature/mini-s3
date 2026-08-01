# Stage 02 · Bucket state and deterministic IDs

### Goal

Introduce the Bucket aggregate, legal versioning transitions, and deterministic identities.

??? note "Deliverable files"
    - `src/minis3/bucket.py`
    - `tests/test_bucket.py`

### The problem at this point

Stage 01 can describe one value but cannot decide what PUT or DELETE does to an existing history. Those decisions must live together; otherwise service, storage, and listing code could each implement a different versioning rule.

### Failure preview

The focused contract writes an unversioned value, enables versioning, writes again, suspends versioning, and then attempts to return to `UNVERSIONED`. If that final transition succeeds, named history can be silently reinterpreted as if versioning never existed. The expected `ValueError` locks the state machine before persistence complicates it.

### Basic concepts

An aggregate is the owner of a related set of state transitions. Here one `Bucket` owns its versioning state and every per-key `ObjectRecord`. `UNVERSIONED` means versioning has never been enabled; `SUSPENDED` means it was enabled and new writes use the public `null` slot while named history remains.

Public `version_id` and internal `storage_id` solve different problems. A suspended bucket may reuse public ID `null`, but immutable disk artifacts still need unique internal names. A monotonic injected sequence produces both forms reproducibly.

### Why this mechanism is necessary

Scattering branches across callers would allow illegal transitions and inconsistent replacement rules. Centralizing them in Bucket makes PUT, GET, and DELETE operate on one history model. Deterministic IDs also let restart recovery resume after the largest published sequence instead of relying on random values.

### Runtime mental model

A caller supplies a command and `SequenceCounter`. Bucket validates its state, obtains one sequence, constructs a new version or marker, and replaces the exact key's immutable `ObjectRecord`. Enabled writes prepend history; unversioned and suspended writes replace only the `null` slot.

### File-by-file walkthrough

#### `src/minis3/bucket.py`

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

##### What it is and why it appears

This mutable aggregate is the single owner of legal versioning changes and per-key histories. Persistence remains outside it.

##### Runtime role

Service code will call `set_versioning`, `put`, `get`, and `delete`. Each method turns one current Bucket state into the next state or raises before mutation.

##### Key code

```python
if self.versioning is VersioningState.ENABLED:
    versions = (version, *old.versions)
else:
```

##### Statement understanding

Enabled PUT preserves every earlier version by prepending. The `else` branch deliberately replaces the public `null` slot while retaining named history; treating both branches alike would break suspended semantics.

#### `tests/test_bucket.py`

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

##### What it is and why it appears

This contract exercises the aggregate before service and disk layers can hide the source of an error.

##### Runtime role

It proves the same sequence produces `null/e00000001` and then `v00000002/e00000002`, and it locks the forbidden backward transition.

##### Key code

```python
with pytest.raises(ValueError):
    bucket.set_versioning(VersioningState.UNVERSIONED)
```

##### Statement understanding

The failure is part of domain behavior, not merely validation style: once named versions can exist, “never versioned” is no longer a truthful state.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`. It proves the focused transition and identity contract, but not disk recovery or concurrent service calls.

### Durable takeaways

Bucket owns history transitions; public version identity and internal artifact identity are separate; enabled and suspended are not interchangeable.

### Explain it in your own words

The Bucket aggregate prevents every caller from inventing its own versioning behavior. It uses one deterministic sequence to order changes, keeps named history when required, and refuses transitions that would make existing history impossible to interpret.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-01...stage-02)

After finishing, use `git checkout stage-02` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/02-bucket-state/stage.patch)
