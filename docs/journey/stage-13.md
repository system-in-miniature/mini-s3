# Stage 13 · Conditional requests and CAS

### Goal

Turn ETags into cache validators and serialized compare-and-swap preconditions.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/conditional.py`
- `src/minis3/errors.py`
- `src/minis3/store.py`
- `tests/test_conditional.py`

### Mechanism walkthrough

#### Ownership and flow

Pure helpers evaluate ETag syntax; `MiniS3` holds one lock across reading the current visible ETag, checking the precondition, and publishing the mutation.

#### Failure and debugging

Separate matching errors from serialization errors. If two conditional writers both win, comparison and mutation escaped the same critical section.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `src/minis3/conditional.py`

ETag precondition matching rules.

Called by `MiniS3` as a policy function; receives explicit values and returns a decision for the service to apply.

**Changed anchors:** `etag_matches`, `require_if_match`, `require_if_none_match`

??? note "File diff: src/minis3/conditional.py"
    ```diff
    diff --git a/src/minis3/conditional.py b/src/minis3/conditional.py
    new file mode 100644
    index 0000000..d13ccf3
    --- /dev/null
    +++ b/src/minis3/conditional.py
    @@ -0,0 +1,35 @@
    +"""Pure HTTP-style ETag precondition evaluation.
    +
    +The service evaluates these functions while holding its mutation lock. That
    +placement matters: checking an ETag and publishing a replacement must be one
    +serialized compare-and-swap operation, not two individually safe calls.
    +"""
    +
    +from __future__ import annotations
    +
    +from .errors import NotModified, PreconditionFailed
    +
    +
    +def etag_matches(condition: str, current_etag: str | None) -> bool:
    +    """Return whether a simplified ETag header matches the current object."""
    +
    +    candidates = tuple(item.strip() for item in condition.split(","))
    +    if "*" in candidates:
    +        return current_etag is not None
    +    return current_etag is not None and current_etag in candidates
    +
    +
    +def require_if_match(current_etag: str | None, condition: str | None) -> None:
    +    """Raise S3's named 412 outcome when If-Match is not satisfied."""
    +
    +    if condition is not None and not etag_matches(condition, current_etag):
    +        raise PreconditionFailed(condition)
    +
    +
    +def require_if_none_match(
    +    current_etag: str | None, condition: str | None
    +) -> None:
    +    """Raise the body-less 304 control outcome when a cached ETag matches."""
    +
    +    if condition is not None and etag_matches(condition, current_etag):
    +        raise NotModified(condition)
    ```

#### `src/minis3/errors.py`

Shared domain failure vocabulary.

Constructed by bucket/service code and returned upward without owning I/O; inspect field values when state is correct but results look wrong.

**Changed anchors:** `PreconditionFailed`, `NotModified`

??? note "File diff: src/minis3/errors.py"
    ```diff
    diff --git a/src/minis3/errors.py b/src/minis3/errors.py
    index 9db3b4c..5f255e0 100644
    --- a/src/minis3/errors.py
    +++ b/src/minis3/errors.py
    @@ -43,3 +43,11 @@ class InvalidPartOrder(MiniS3Error):

     class EntityTooSmall(MiniS3Error):
         """A non-final multipart part is below the configured minimum size."""
    +
    +
    +class PreconditionFailed(MiniS3Error):
    +    """An If-Match condition failed (the S3-shaped HTTP 412 outcome)."""
    +
    +
    +class NotModified(MiniS3Error):
    +    """An If-None-Match condition matched (the HTTP 304 control outcome)."""
    ```

#### `src/minis3/store.py`

Application service coordinating domain and persistence.

Receives public calls, owns locking and orchestration, then delegates to domain, projection, and storage boundaries.

**Changed anchors:** `put_object`, `_current_etag`, `_addressed_etag`, `_bucket`

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index 9b50aa2..e47e1ac 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -8,8 +8,9 @@ from pathlib import Path
     from threading import RLock
     from time import time

    +from .conditional import require_if_match, require_if_none_match
     from .bucket import Bucket, SequenceCounter, VersioningState
    -from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    +from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket, NoSuchKey, NoSuchVersion
     from .listing import ListObjectsResult, ListObjectVersionsResult, list_object_versions, list_objects
     from .model import ObjectVersion, Version
     from .multipart import (
    @@ -78,20 +79,39 @@ class MiniS3:
                 self._buckets[name] = candidate


    -    def put_object(self, bucket: str, key: str, body: bytes) -> Version:
    +    def put_object(
    +        self,
    +        bucket: str,
    +        key: str,
    +        body: bytes,
    +        *,
    +        if_match: str | None = None,
    +    ) -> Version:
             with self._lock:
                 candidate = deepcopy(self._bucket(bucket))
    -            result = candidate.put(key, body, self._counter)
    +            require_if_match(self._current_etag(candidate, key), if_match)
    +            result = candidate.put(
    +                key, body, self._counter, now=self._clock()
    +            )
                 self._storage.persist_bucket(candidate)
                 self._buckets[bucket] = candidate
                 return result


         def get_object(
    -        self, bucket: str, key: str, *, version_id: str | None = None
    +        self,
    +        bucket: str,
    +        key: str,
    +        *,
    +        version_id: str | None = None,
    +        if_match: str | None = None,
    +        if_none_match: str | None = None,
         ) -> Version:
             with self._lock:
    -            return self._bucket(bucket).get(key, version_id)
    +            result = self._bucket(bucket).get(key, version_id)
    +            require_if_match(result.etag, if_match)
    +            require_if_none_match(result.etag, if_none_match)
    +            return result


         def head_object(
    @@ -103,11 +123,21 @@ class MiniS3:


         def delete_object(
    -        self, bucket: str, key: str, *, version_id: str | None = None
    +        self,
    +        bucket: str,
    +        key: str,
    +        *,
    +        version_id: str | None = None,
    +        if_match: str | None = None,
         ) -> ObjectVersion | None:
             with self._lock:
                 candidate = deepcopy(self._bucket(bucket))
    -            result = candidate.delete(key, self._counter, version_id)
    +            require_if_match(
    +                self._addressed_etag(candidate, key, version_id), if_match
    +            )
    +            result = candidate.delete(
    +                key, self._counter, version_id, now=self._clock()
    +            )
                 self._storage.persist_bucket(candidate)
                 self._buckets[bucket] = candidate
                 return result
    @@ -220,6 +250,24 @@ class MiniS3:
                 self._storage.remove_multipart_upload(bucket, key, upload_id)


    +    @staticmethod
    +    def _current_etag(bucket: Bucket, key: str) -> str | None:
    +        try:
    +            return bucket.get(key).etag
    +        except NoSuchKey:
    +            return None
    +
    +
    +    @staticmethod
    +    def _addressed_etag(
    +        bucket: Bucket, key: str, version_id: str | None
    +    ) -> str | None:
    +        try:
    +            return bucket.get(key, version_id).etag
    +        except (NoSuchKey, NoSuchVersion):
    +            return None
    +
    +
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
    ```

#### `src/minis3/__init__.py`

Supported public package surface.

Reached by user imports; wiring errors appear as missing names before any runtime flow starts.

**Changed anchors:** configuration, export, or documentation change

??? note "File diff: src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 0c23aea..3f6e582 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -7,3 +7,4 @@ from .storage import InjectedCrash
     from .listing import ListedObject, ListedVersion, ListObjectsResult, ListObjectVersionsResult
     from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder, NoSuchUpload
     from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
    +from .errors import NotModified, PreconditionFailed
    ```

#### `tests/test_conditional.py`

Executable proof of the stage behavior.

Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

**Changed anchors:** `test_get_if_none_match_has_304_semantics_and_if_match_has_412`, `test_put_and_delete_if_match_compare_against_current_visible_etag`, `test_if_match_wildcard_requires_a_current_visible_object`, `test_two_conditional_writers_have_exactly_one_winner`, `writer`

??? note "File diff: tests/test_conditional.py"
    ```diff
    diff --git a/tests/test_conditional.py b/tests/test_conditional.py
    new file mode 100644
    index 0000000..137e7a1
    --- /dev/null
    +++ b/tests/test_conditional.py
    @@ -0,0 +1,81 @@
    +"""Conditional requests turn current ETags into an object-level CAS token."""
    +
    +from concurrent.futures import ThreadPoolExecutor
    +from pathlib import Path
    +from threading import Barrier
    +
    +import pytest
    +
    +from minis3 import MiniS3, NoSuchKey, NotModified, PreconditionFailed
    +
    +
    +def test_get_if_none_match_has_304_semantics_and_if_match_has_412(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    current = store.put_object("b", "k", b"value")
    +
    +    with pytest.raises(NotModified):
    +        store.get_object("b", "k", if_none_match=current.etag)
    +    with pytest.raises(NotModified):
    +        store.get_object("b", "k", if_none_match="*")
    +    with pytest.raises(PreconditionFailed):
    +        store.get_object(
    +            "b", "k", if_match='"00000000000000000000000000000000"'
    +        )
    +    assert store.get_object("b", "k", if_match=current.etag) == current
    +
    +
    +def test_put_and_delete_if_match_compare_against_current_visible_etag(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    initial = store.put_object("b", "k", b"old")
    +    winner = store.put_object("b", "k", b"new", if_match=initial.etag)
    +
    +    with pytest.raises(PreconditionFailed):
    +        store.put_object("b", "k", b"stale", if_match=initial.etag)
    +    with pytest.raises(PreconditionFailed):
    +        store.delete_object("b", "k", if_match=initial.etag)
    +
    +    removed = store.delete_object("b", "k", if_match=winner.etag)
    +    assert removed is None
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("b", "k")
    +
    +
    +def test_if_match_wildcard_requires_a_current_visible_object(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +
    +    with pytest.raises(PreconditionFailed):
    +        store.put_object("b", "missing", b"x", if_match="*")
    +    with pytest.raises(PreconditionFailed):
    +        store.delete_object("b", "missing", if_match="*")
    +
    +    store.put_object("b", "present", b"x")
    +    assert store.put_object("b", "present", b"y", if_match="*").body == b"y"
    +
    +
    +def test_two_conditional_writers_have_exactly_one_winner(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    observed = store.put_object("b", "counter", b"0").etag
    +    barrier = Barrier(2)
    +
    +    def writer(value: bytes) -> str:
    +        barrier.wait()
    +        try:
    +            store.put_object("b", "counter", value, if_match=observed)
    +        except PreconditionFailed:
    +            return "412"
    +        return "stored"
    +
    +    with ThreadPoolExecutor(max_workers=2) as pool:
    +        outcomes = list(pool.map(writer, (b"writer-a", b"writer-b")))
    +
    +    assert sorted(outcomes) == ["412", "stored"]
    +    assert store.get_object("b", "counter").body in {b"writer-a", b"writer-b"}
    +
    ```

### Verification evidence

`uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`

This stage adds 4 executable case(s), anchored at `test_get_if_none_match_has_304_semantics_and_if_match_has_412`, `test_put_and_delete_if_match_compare_against_current_visible_etag`, `test_if_match_wildcard_requires_a_current_visible_object`, `test_two_conditional_writers_have_exactly_one_winner`. Run them after the mechanism walkthrough; the cumulative gate also reruns every earlier stage contract.

### Concept check

Which invariant must remain true after this stage?

??? note "Answer"
    The comparison and publication must share one critical section or two writers can both win.

### Code-reading check

Start at `etag_matches` in `src/minis3/conditional.py`: what state or value enters this boundary, and which owner consumes the result next?

??? note "Answer"
    Called by `MiniS3` as a policy function; receives explicit values and returns a decision for the service to apply.

### Interview-ready summary

The comparison and publication must share one critical section or two writers can both win.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/07-conditional.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-12...stage-13)

After finishing, use `git checkout stage-13` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/13-conditional-cas/stage.patch)
