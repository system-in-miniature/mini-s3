# Stage 13 · Conditional requests and CAS

### Goal

Use ETags as cache validators and serialized compare-and-swap preconditions for reads and mutations.

### Deliverable files

??? note "Show deliverable files"
    - `src/minis3/__init__.py`
    - `src/minis3/conditional.py`
    - `src/minis3/errors.py`
    - `src/minis3/store.py`
    - `tests/test_conditional.py`

### The problem at this point

ETags exist but callers cannot make an operation conditional on the value they observed. A stale writer can overwrite a newer value, and a cache cannot ask whether its copy is still current without downloading the body again.

### Failure preview

The concurrency contract starts two writers with the same initial ETag. Exactly one may pass `If-Match`; the second must see the changed current ETag and fail. If the check occurs outside the mutation lock, both can validate stale state and both appear to win.

### Basic concepts

`If-None-Match` on GET is a cache validator: a match means the representation is not modified (304-shaped). `If-Match` is a precondition: mismatch means the requested operation cannot be applied to the addressed current state (412-shaped).

Compare-and-swap means “change only if the current identity still equals what I observed.” Correctness depends on checking and mutating within one serialized critical section, not just on comparing strings.

### Why this mechanism is necessary

Without preconditions, read-modify-write clients lose updates. Without distinct 304/412 failures, callers cannot tell a successful cache validation from a rejected mutation. Central match helpers keep wildcard and comma-list behavior consistent.

### Runtime mental model

The service acquires its lock, resolves the current or addressed ETag, applies `require_if_match`/`require_if_none_match`, and only then reads or mutates. A successful PUT changes the ETag before the next waiting writer performs its check.

### File-by-file walkthrough

#### `src/minis3/conditional.py`

##### What it is and why it appears

This pure policy module parses ETag conditions and raises the correct semantic failure.

##### Runtime role

Store supplies the current ETag; the helpers decide match, precondition failure, or not-modified without owning locks or state.

##### Key code

```python
if condition is not None and not etag_matches(condition, current_etag):
    raise PreconditionFailed(condition)
```

##### Statement understanding

Absent condition means no guard. A present nonmatch must stop the operation before mutation; returning `False` for the caller to ignore would weaken the contract.

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

##### What it is and why it appears

The failure vocabulary gains distinct precondition-failed and not-modified outcomes.

##### Runtime role

Protocol adapters can later map them to 412 and 304 without embedding HTTP in the domain service.

##### Key code

```python
class NotModified(MiniS3Error):
```

##### Statement understanding

Not-modified is control-flow evidence for a validator, not the same error as a mutation rejected against stale state.

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

##### What it is and why it appears

Public GET, PUT, and DELETE accept conditional parameters and evaluate them inside existing locks.

##### Runtime role

It owns atomicity between current-ETag lookup, precondition decision, and any subsequent Bucket mutation/publication.

##### Key code

```python
require_if_match(self._current_etag(candidate, key), if_match)
```

##### Statement understanding

The check reads from the candidate snapshot while the service lock is held. No other writer can change the current visible ETag between this line and mutation.

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

##### What it is and why it appears

Conditional failures become part of the supported API.

##### Runtime role

Callers catch semantic outcomes from the package root; match helpers remain internal policy.

##### Statement understanding

Exposing outcome types but not parsing internals keeps the public surface small.

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

##### What it is and why it appears

Four contracts cover GET validators, mutation guards, wildcard behavior, and the two-writer CAS race.

##### Runtime role

The threaded test proves serialization behavior that a sequential helper unit test cannot establish.

##### Key code

```python
assert sorted(outcomes) == ["412", "stored"]
```

##### Statement understanding

One `stored` and one `412` is the externally visible CAS guarantee. Two stored outcomes would prove the check and mutation were not atomic.

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

Run `uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`. The cases prove matching forms, failure meanings, mutation guards, and one-winner concurrency.

### Durable takeaways

ETag comparison becomes safe concurrency control only when check and mutation share the same lock. 304-style validation and 412-style rejection are different outcomes.

### Explain it in your own words

Conditional requests let a caller act on the exact value it observed. MiniS3 evaluates the ETag guard inside the service's mutation lock, so one writer can commit and every stale competitor then fails against the new current ETag instead of overwriting it.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/07-conditional.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-12...stage-13)

After finishing, use `git checkout stage-13` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/13-conditional-cas/stage.patch)
