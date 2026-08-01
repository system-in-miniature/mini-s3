# Stage 04 · Object service facade

### Goal

Join Bucket and DiskStorage behind one locked public service for bucket and object operations.

??? note "Deliverable files"
    - `src/minis3/__init__.py`
    - `src/minis3/store.py`
    - `tests/test_storage.py`
    - `tests/test_versioning.py`

### The problem at this point

The domain can calculate a next Bucket and storage can publish it, but callers still have to coordinate both. Without a service owner, one code path could mutate memory without persistence while another could race halfway through a transition.

### Failure preview

The restart contract writes two versions, opens a fresh `MiniS3`, reads both bodies, then writes again and requires a new ID. It exposes two distinct bugs at once: state not published to disk, or the recovered sequence counter reusing an old identity.

### Basic concepts

An application service coordinates existing owners; it does not absorb their responsibilities. Bucket still decides legal history, DiskStorage still decides publication and recovery, and `MiniS3` owns the public operation, lock, lookup, and ordering between them.

The implementation mutates a deep-copied candidate, persists it, and only then swaps the in-memory Bucket reference. Thus a publication failure leaves the previously visible in-memory state intact.

### Why this mechanism is necessary

Locking only Bucket or only disk is insufficient because a public mutation spans both. One service lock serializes the read-check-mutate-publish sequence, while candidate publication avoids exposing uncommitted memory.

### Runtime mental model

`put_object` acquires the lock, resolves a Bucket, copies it, delegates PUT to the candidate, persists the candidate, swaps it into `_buckets`, and returns the Version. GET and HEAD read under the same lock; HEAD reuses GET because this protocol-free model returns the same metadata value.

### File-by-file walkthrough

#### `src/minis3/store.py`

##### What it is and why it appears

This is the public application boundary that coordinates locking, aggregate transitions, persistence, and recovery.

##### Runtime role

Every public bucket/object call enters here. Successful mutations cross Bucket then DiskStorage; reads resolve the current in-memory aggregate.

##### Key code

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
```

##### Statement understanding

Publication occurs before the candidate becomes the process-visible Bucket. Reversing these lines would let a failed disk write leak state that disappears after restart.

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    new file mode 100644
    index 0000000..5d418b8
    --- /dev/null
    +++ b/src/minis3/store.py
    @@ -0,0 +1,104 @@
    +"""Public service facade joining buckets, object state, and list projections."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable
    +from copy import deepcopy
    +from pathlib import Path
    +from threading import RLock
    +
    +from .bucket import Bucket, SequenceCounter, VersioningState
    +from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    +from .model import ObjectVersion, Version
    +from .storage import DiskStorage
    +
    +
    +class MiniS3:
    +    """A deterministic collection of strongly consistent buckets."""
    +
    +    def __init__(
    +        self,
    +        root: str | Path,
    +        *,
    +        counter: Callable[[], int] | None = None,
    +        crash_injector: Callable[[str], None] | None = None,
    +    ) -> None:
    +        self.root = Path(root)
    +        self._counter = counter or SequenceCounter()
    +        self._storage = DiskStorage(root, crash_injector=crash_injector)
    +        self._buckets, maximum_sequence = self._storage.load_buckets()
    +        ensure = getattr(self._counter, "ensure_at_least", None)
    +        if ensure is not None:
    +            ensure(maximum_sequence + 1)
    +        self._lock = RLock()
    +
    +
    +    def create_bucket(self, name: str) -> None:
    +        with self._lock:
    +            if name in self._buckets:
    +                raise BucketAlreadyExists(name)
    +            bucket = Bucket(name)
    +            self._storage.create_bucket(bucket)
    +            self._buckets[name] = bucket
    +
    +
    +    def delete_bucket(self, name: str) -> None:
    +        with self._lock:
    +            bucket = self._bucket(name)
    +            if bucket.records:
    +                raise BucketNotEmpty(name)
    +            self._storage.delete_bucket(name)
    +            del self._buckets[name]
    +
    +
    +    def set_bucket_versioning(
    +        self, name: str, state: VersioningState | str
    +    ) -> None:
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(name))
    +            candidate.set_versioning(state)
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[name] = candidate
    +
    +
    +    def put_object(self, bucket: str, key: str, body: bytes) -> Version:
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(bucket))
    +            result = candidate.put(key, body, self._counter)
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[bucket] = candidate
    +            return result
    +
    +
    +    def get_object(
    +        self, bucket: str, key: str, *, version_id: str | None = None
    +    ) -> Version:
    +        with self._lock:
    +            return self._bucket(bucket).get(key, version_id)
    +
    +
    +    def head_object(
    +        self, bucket: str, key: str, *, version_id: str | None = None
    +    ) -> Version:
    +        """Return object metadata; M1 reuses the immutable Version value."""
    +
    +        return self.get_object(bucket, key, version_id=version_id)
    +
    +
    +    def delete_object(
    +        self, bucket: str, key: str, *, version_id: str | None = None
    +    ) -> ObjectVersion | None:
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(bucket))
    +            result = candidate.delete(key, self._counter, version_id)
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[bucket] = candidate
    +            return result
    +
    +
    +    def _bucket(self, name: str) -> Bucket:
    +        try:
    +            return self._buckets[name]
    +        except KeyError as exc:
    +            raise NoSuchBucket(name) from exc
    +
    ```

#### `src/minis3/__init__.py`

##### What it is and why it appears

The package now exports `MiniS3` and versioning state in addition to the value model.

##### Runtime role

It establishes the intended entry point; callers no longer need to assemble Bucket and DiskStorage themselves.

##### Statement understanding

Public export is API wiring, not proof of runtime behavior. The service tests below provide that evidence.

??? note "File diff: src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 8a3d1c7..11378e1 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -1,3 +1,6 @@
     """Public API for the MiniS3 teaching implementation."""
     from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
    +from .bucket import SequenceCounter, VersioningState
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
    +from .store import MiniS3
    +from .storage import InjectedCrash
    ```

#### `tests/test_storage.py`

##### What it is and why it appears

These contracts exercise persistence through the public service, including restart, crash injection, bucket deletion, and sequence recovery.

##### Runtime role

They detect gaps between in-memory success and reopened state. This is where orchestration and storage meet.

##### Key code

```python
assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
```

##### Statement understanding

Addressing the old version after constructing `reopened` proves both the version history and its bytes survived publication; checking only the latest value would be weaker.

??? note "File diff: tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    new file mode 100644
    index 0000000..c96a7a6
    --- /dev/null
    +++ b/tests/test_storage.py
    @@ -0,0 +1,32 @@
    +"""Disk tests pin the manifest publication crash boundary."""
    +
    +from pathlib import Path
    +import pytest
    +from minis3 import InjectedCrash, MiniS3, NoSuchKey, SequenceCounter
    +from minis3.bucket import Bucket
    +from minis3.storage import atomic, disk
    +from minis3.storage.disk import DiskStorage
    +
    +
    +class CrashOnce:
    +    def __init__(self, target: str) -> None:
    +        self.target = target
    +        self.used = False
    +
    +    def __call__(self, point: str) -> None:
    +        if point == self.target and not self.used:
    +            self.used = True
    +            raise InjectedCrash(point)
    +
    +
    +def test_restart_restores_versions_bodies_and_counter(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    first = store.put_object("b", "k", b"one")
    +
    +    reopened = MiniS3(tmp_path)
    +    second = reopened.put_object("b", "k", b"two")
    +
    +    assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
    +    assert second.version_id != first.version_id
    ```

#### `tests/test_versioning.py`

##### What it is and why it appears

This file locks the full public versioning state machine and DELETE meanings.

##### Runtime role

It distinguishes unversioned deletion, marker creation, specific-version deletion, latest-marker 404 behavior, and retained named history.

##### Key code

```python
assert bucket.get("k", historical.version_id) == historical
```

##### Statement understanding

The defensive case proves an unversioned delete cannot erase a named version already present in recovered or externally constructed history.

??? note "File diff: tests/test_versioning.py"
    ```diff
    diff --git a/tests/test_versioning.py b/tests/test_versioning.py
    new file mode 100644
    index 0000000..389e45d
    --- /dev/null
    +++ b/tests/test_versioning.py
    @@ -0,0 +1,109 @@
    +"""Versioning is the central state-machine contract of M1."""
    +
    +from pathlib import Path
    +import pytest
    +from minis3 import BucketNotEmpty, MiniS3, NoSuchKey, NoSuchVersion, SequenceCounter, VersioningState
    +from minis3.bucket import Bucket
    +
    +
    +@pytest.mark.parametrize(
    +    ("initial", "requested", "allowed"),
    +    [
    +        (VersioningState.UNVERSIONED, VersioningState.UNVERSIONED, True),
    +        (VersioningState.UNVERSIONED, VersioningState.ENABLED, True),
    +        (VersioningState.UNVERSIONED, VersioningState.SUSPENDED, False),
    +        (VersioningState.ENABLED, VersioningState.UNVERSIONED, False),
    +        (VersioningState.ENABLED, VersioningState.ENABLED, True),
    +        (VersioningState.ENABLED, VersioningState.SUSPENDED, True),
    +        (VersioningState.SUSPENDED, VersioningState.UNVERSIONED, False),
    +        (VersioningState.SUSPENDED, VersioningState.ENABLED, True),
    +        (VersioningState.SUSPENDED, VersioningState.SUSPENDED, True),
    +    ],
    +)
    +def test_versioning_state_machine_exhaustive(
    +    initial: VersioningState,
    +    requested: VersioningState,
    +    allowed: bool,
    +) -> None:
    +    bucket = Bucket("b", versioning=initial)
    +
    +    if allowed:
    +        bucket.set_versioning(requested)
    +        assert bucket.versioning is requested
    +    else:
    +        with pytest.raises(ValueError):
    +            bucket.set_versioning(requested)
    +        assert bucket.versioning is initial
    +
    +
    +def test_unversioned_delete_defensively_preserves_named_history() -> None:
    +    bucket = Bucket("b")
    +    bucket.set_versioning(VersioningState.ENABLED)
    +    historical = bucket.put("k", b"named", SequenceCounter())
    +    bucket.versioning = VersioningState.UNVERSIONED
    +
    +    bucket.delete("k", SequenceCounter(10))
    +
    +    assert bucket.get("k", historical.version_id) == historical
    +
    +
    +def test_enabled_puts_stack_and_delete_marker_hides_history(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter())
    +    store.create_bucket("photos")
    +    null = store.put_object("photos", "cat.jpg", b"before")
    +    store.set_bucket_versioning("photos", VersioningState.ENABLED)
    +    first = store.put_object("photos", "cat.jpg", b"one")
    +    second = store.put_object("photos", "cat.jpg", b"two")
    +    marker = store.delete_object("photos", "cat.jpg")
    +
    +    assert [null.version_id, first.version_id, second.version_id] == [
    +        "null",
    +        "v00000002",
    +        "v00000003",
    +    ]
    +    assert marker is not None and marker.version_id == "v00000004"
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("photos", "cat.jpg")
    +    assert store.get_object(
    +        "photos", "cat.jpg", version_id=second.version_id
    +    ).body == b"two"
    +    assert store.head_object(
    +        "photos", "cat.jpg", version_id=first.version_id
    +    ).etag == first.etag
    +
    +
    +def test_specific_delete_removes_only_addressed_version(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter())
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    store.put_object("b", "k", b"old")
    +    new = store.put_object("b", "k", b"new")
    +
    +    removed = store.delete_object("b", "k", version_id=new.version_id)
    +
    +    assert removed == new
    +    assert store.get_object("b", "k").body == b"old"
    +    with pytest.raises(NoSuchVersion):
    +        store.get_object("b", "k", version_id=new.version_id)
    +
    +
    +def test_latest_marker_is_404_even_when_older_data_exists(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    old = store.put_object("b", "k", b"still here")
    +    marker = store.delete_object("b", "k")
    +
    +    with pytest.raises(NoSuchKey):
    +        store.head_object("b", "k")
    +    assert store.get_object("b", "k", version_id=old.version_id).body == b"still here"
    +    assert store.delete_object("b", "k", version_id=marker.version_id) == marker
    +    assert store.get_object("b", "k").body == b"still here"
    +
    +
    +def test_nonempty_bucket_cannot_be_deleted(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.put_object("b", "k", b"value")
    +    with pytest.raises(BucketNotEmpty):
    +        store.delete_bucket("b")
    ```

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/04-object-service/tests.txt)`. Fifteen cases cover service orchestration and version behavior. They do not yet prove listing projections or injected crash outcomes around the manifest rename.

### Durable takeaways

The service owns orchestration and locking; Bucket owns domain transitions; storage owns durability; persist-before-swap keeps memory aligned with committed state.

### Explain it in your own words

`MiniS3` turns separate domain and storage components into one consistent public operation. It serializes the whole transition, publishes a candidate Bucket before exposing it, and therefore keeps current memory and restart-visible state on the same side of a failed write.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/02-objects-etag.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-03...stage-04)

After finishing, use `git checkout stage-04` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/04-object-service/stage.patch)
