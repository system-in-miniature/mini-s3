# Stage 06 · Listing and the directory illusion

### Goal

Derive current contents and common prefixes from flat keys, with query-bound opaque pagination tokens.

??? note "Deliverable files"
    - `src/minis3/__init__.py`
    - `src/minis3/listing.py`
    - `src/minis3/store.py`
    - `tests/test_listing.py`

### The problem at this point

Version listing can expose history, but normal object listing still has no answer for prefix, delimiter, or pagination. Treating slash-containing keys as real directories would contradict Stage 01 and create state that S3 does not store.

### Test contract

#### See the failure first

The delimiter contract stores `a.txt`, `raw`, and several `photos/...` keys. Listing the root with delimiter `/` must return two contents plus exactly one `photos/` common prefix. If the implementation walks directories or returns every photo key, the externally visible projection is wrong.

??? note "File diff: tests/test_listing.py"
    ```diff
    diff --git a/tests/test_listing.py b/tests/test_listing.py
    new file mode 100644
    index 0000000..741dacb
    --- /dev/null
    +++ b/tests/test_listing.py
    @@ -0,0 +1,93 @@
    +"""Listing tests make the directory illusion and ordering observable."""
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minis3 import InvalidContinuationToken, MiniS3
    +
    +
    +def _populated_store(root: Path) -> MiniS3:
    +    store = MiniS3(root)
    +    store.create_bucket("b")
    +    for key in ("a.txt", "photos/2025/a.jpg", "photos/2026/b.jpg", "raw"):
    +        store.put_object("b", key, key.encode())
    +    return store
    +
    +
    +def test_delimiter_derives_common_prefixes_from_flat_keys(tmp_path: Path) -> None:
    +    store = _populated_store(tmp_path)
    +
    +    root = store.list_objects("b", delimiter="/")
    +    photos = store.list_objects("b", prefix="photos/", delimiter="/")
    +    flat = store.list_objects("b", prefix="photos/")
    +
    +    assert [item.key for item in root.contents] == ["a.txt", "raw"]
    +    assert root.common_prefixes == ("photos/",)
    +    assert photos.common_prefixes == ("photos/2025/", "photos/2026/")
    +    assert [item.key for item in flat.contents] == [
    +        "photos/2025/a.jpg",
    +        "photos/2026/b.jpg",
    +    ]
    +
    +
    +def test_pagination_counts_contents_and_prefixes_and_token_is_opaque(
    +    tmp_path: Path,
    +) -> None:
    +    store = _populated_store(tmp_path)
    +    first = store.list_objects("b", delimiter="/", max_keys=2)
    +    second = store.list_objects(
    +        "b", delimiter="/", max_keys=2, continuation_token=first.next_token
    +    )
    +
    +    assert first.key_count == 2
    +    assert first.next_token is not None
    +    assert "photos/" not in first.next_token
    +    assert {
    +        *(item.key for item in first.contents),
    +        *first.common_prefixes,
    +        *(item.key for item in second.contents),
    +        *second.common_prefixes,
    +    } == {"a.txt", "photos/", "raw"}
    +    assert second.next_token is None
    +
    +
    +def test_current_listing_hides_key_behind_delete_marker(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    store.put_object("b", "hidden", b"value")
    +    store.delete_object("b", "hidden")
    +
    +    assert store.list_objects("b").contents == ()
    +
    +
    +def test_version_listing_flattens_versions_and_marks_latest(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    one = store.put_object("b", "a", b"one")
    +    two = store.put_object("b", "a", b"two")
    +    marker = store.delete_object("b", "a")
    +
    +    items = store.list_object_versions("b").versions
    +
    +    assert [item.version_id for item in items] == [
    +        marker.version_id,
    +        two.version_id,
    +        one.version_id,
    +    ]
    +    assert [item.is_latest for item in items] == [True, False, False]
    +    assert items[0].is_delete_marker is True
    +
    +
    +def test_malformed_or_query_mismatched_tokens_are_rejected(tmp_path: Path) -> None:
    +    store = _populated_store(tmp_path)
    +    first = store.list_objects("b", max_keys=1)
    +
    +    with pytest.raises(InvalidContinuationToken):
    +        store.list_objects("b", continuation_token="not-base64!")
    +    with pytest.raises(InvalidContinuationToken):
    +        store.list_objects(
    +            "b", prefix="different", continuation_token=first.next_token
    +        )
    ```

**What this test locks**

Five contracts cover directory illusion, combined pagination, marker hiding, flattened version history, and invalid tokens.

**How it constructs the counterexample**

They build state through `MiniS3` and inspect public results, so the examples connect model semantics to the final read view.

**Key test statement**

```python
assert root.common_prefixes == ("photos/",)
```

**What a failure means**

Several flat keys collapse into one projected prefix at the root. The tuple does not mean a `photos/` object or directory was stored.

### Basic concepts

`prefix` filters keys by exact string start. `delimiter` groups the remaining suffix at its first delimiter into a `common_prefix`; this is a computed view, not a stored folder. A page counts both returned objects and common prefixes because both consume result slots.

A continuation token is an opaque cursor. MiniS3 encodes the offset together with prefix and delimiter, so a token from one query cannot be replayed against another and silently skip different results.

### Why this mechanism is necessary

Exposing a raw numeric offset leaks implementation and allows query mismatch. Treating common prefixes as objects would confuse HEAD/GET and deletion. One pure projection keeps flat storage intact while producing familiar directory-like navigation.

### Runtime mental model

The service locks a Bucket snapshot and calls `list_objects`. The function selects each key's current visible data, applies prefix and delimiter projection, sorts the combined entries, decodes a query-bound offset, slices one page, and creates the next opaque token when more entries remain.

### Mechanism blocks

#### Directory-like listing projection

Derive prefix, delimiter, pagination, and continuation behavior from flat exact keys without creating directories.

??? note "File diff: src/minis3/listing.py"
    ```diff
    diff --git a/src/minis3/listing.py b/src/minis3/listing.py
    index 3c40e0d..c6e95b3 100644
    --- a/src/minis3/listing.py
    +++ b/src/minis3/listing.py
    @@ -1,13 +1,43 @@
    -"""Version-history projection over MiniS3 records."""
    +"""Strongly consistent projections over MiniS3's flat key map.

    +``delimiter`` does not traverse directories. It partitions matching strings:
    +the first delimiter after ``prefix`` turns the matching key into a
    +``common_prefix``; otherwise the key is returned as content. This projection
    +is the entire "directory illusion."
    +"""

     from __future__ import annotations

    -
    +from base64 import urlsafe_b64decode, urlsafe_b64encode
     from dataclasses import dataclass
    +import json
    +
    +from .errors import InvalidContinuationToken
    +from .model import DeleteMarker, ObjectRecord, Version
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ListedObject:
    +    """Current visible metadata for one exact key."""
    +
    +    key: str
    +    etag: str
    +    size: int
    +    version_id: str
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ListObjectsResult:
    +    """One page of current objects and derived common prefixes."""

    +    contents: tuple[ListedObject, ...]
    +    common_prefixes: tuple[str, ...]
    +    key_count: int
    +    next_token: str | None

    -from .model import ObjectRecord, Version
    +    @property
    +    def is_truncated(self) -> bool:
    +        return self.next_token is not None


     @dataclass(frozen=True, slots=True)
    @@ -29,6 +59,86 @@ class ListObjectVersionsResult:
         versions: tuple[ListedVersion, ...]


    +def _encode_token(offset: int, prefix: str, delimiter: str | None) -> str:
    +    payload = json.dumps(
    +        {"o": offset, "p": prefix, "d": delimiter},
    +        separators=(",", ":"),
    +        sort_keys=True,
    +    ).encode()
    +    return urlsafe_b64encode(payload).decode().rstrip("=")
    +
    +
    +def _decode_token(token: str, prefix: str, delimiter: str | None) -> int:
    +    try:
    +        padded = token + "=" * (-len(token) % 4)
    +        payload = json.loads(urlsafe_b64decode(padded).decode())
    +        if payload != {"o": payload["o"], "p": prefix, "d": delimiter}:
    +            raise ValueError
    +        offset = payload["o"]
    +        if not isinstance(offset, int) or offset < 0:
    +            raise ValueError
    +        return offset
    +    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
    +        raise InvalidContinuationToken(token) from exc
    +
    +
    +def list_objects(
    +    records: dict[str, ObjectRecord],
    +    *,
    +    prefix: str = "",
    +    delimiter: str | None = None,
    +    max_keys: int = 1000,
    +    continuation_token: str | None = None,
    +) -> ListObjectsResult:
    +    """Build one deterministic page from a single in-memory snapshot."""
    +
    +    if max_keys < 0:
    +        raise ValueError("max_keys must be non-negative")
    +    if delimiter == "":
    +        raise ValueError("delimiter must be non-empty")
    +
    +    contents: dict[str, ListedObject] = {}
    +    prefixes: set[str] = set()
    +    for key, record in records.items():
    +        if not key.startswith(prefix) or not record.versions:
    +            continue
    +        current = record.versions[0]
    +        if isinstance(current, DeleteMarker):
    +            continue
    +        suffix = key[len(prefix) :]
    +        if delimiter is not None and delimiter in suffix:
    +            boundary = suffix.index(delimiter) + len(delimiter)
    +            prefixes.add(prefix + suffix[:boundary])
    +        else:
    +            contents[key] = ListedObject(
    +                key, current.etag, current.size, current.version_id
    +            )
    +
    +    combined: list[tuple[str, str]] = [
    +        *((key, "content") for key in contents),
    +        *((item, "prefix") for item in prefixes),
    +    ]
    +    combined.sort()
    +    offset = (
    +        0
    +        if continuation_token is None
    +        else _decode_token(continuation_token, prefix, delimiter)
    +    )
    +    page = combined[offset : offset + max_keys]
    +    next_offset = offset + len(page)
    +    next_token = (
    +        _encode_token(next_offset, prefix, delimiter)
    +        if next_offset < len(combined)
    +        else None
    +    )
    +    return ListObjectsResult(
    +        contents=tuple(contents[key] for key, kind in page if kind == "content"),
    +        common_prefixes=tuple(key for key, kind in page if kind == "prefix"),
    +        key_count=len(page),
    +        next_token=next_token,
    +    )
    +
    +
     def list_object_versions(
         records: dict[str, ObjectRecord],
         *,
    @@ -53,3 +163,4 @@ def list_object_versions(
                     )
                 )
         return ListObjectVersionsResult(tuple(result))
    +
    ```

**What it is and why it appears**

The read-side projection now owns current-object listing, delimiter grouping, and pagination tokens alongside version listing.

**Runtime role**

It consumes Bucket records without mutation and returns immutable `contents`, `common_prefixes`, and `next_token`.

**Key code**

```python
return urlsafe_b64encode(payload).decode().rstrip("=")
```

**Statement understanding**

The token hides the cursor representation. Its payload also contains the query shape, so decoding can reject a cursor that belongs to another prefix or delimiter.

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index 23ddd8e..7c82b41 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -1,4 +1,9 @@
    -"""Public service facade joining buckets, object state, and list projections."""
    +"""Public service facade joining buckets, object state, and list projections.
    +
    +This initial service boundary deliberately resembles an SDK rather than an HTTP
    +server. A future thin protocol adapter can translate these domain values and
    +errors without taking ownership of storage semantics.
    +"""

     from __future__ import annotations

    @@ -9,7 +14,12 @@ from threading import RLock

     from .bucket import Bucket, SequenceCounter, VersioningState
     from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    -from .listing import ListObjectVersionsResult, list_object_versions
    +from .listing import (
    +    ListObjectsResult,
    +    ListObjectVersionsResult,
    +    list_object_versions,
    +    list_objects,
    +)
     from .model import ObjectVersion, Version
     from .storage import DiskStorage

    @@ -33,7 +43,6 @@ class MiniS3:
                 ensure(maximum_sequence + 1)
             self._lock = RLock()

    -
         def create_bucket(self, name: str) -> None:
             with self._lock:
                 if name in self._buckets:
    @@ -42,7 +51,6 @@ class MiniS3:
                 self._storage.create_bucket(bucket)
                 self._buckets[name] = bucket

    -
         def delete_bucket(self, name: str) -> None:
             with self._lock:
                 bucket = self._bucket(name)
    @@ -51,7 +59,6 @@ class MiniS3:
                 self._storage.delete_bucket(name)
                 del self._buckets[name]

    -
         def set_bucket_versioning(
             self, name: str, state: VersioningState | str
         ) -> None:
    @@ -61,7 +68,6 @@ class MiniS3:
                 self._storage.persist_bucket(candidate)
                 self._buckets[name] = candidate

    -
         def put_object(self, bucket: str, key: str, body: bytes) -> Version:
             with self._lock:
                 candidate = deepcopy(self._bucket(bucket))
    @@ -70,14 +76,12 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    -
         def get_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> Version:
             with self._lock:
                 return self._bucket(bucket).get(key, version_id)

    -
         def head_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> Version:
    @@ -85,7 +89,6 @@ class MiniS3:

             return self.get_object(bucket, key, version_id=version_id)

    -
         def delete_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> ObjectVersion | None:
    @@ -96,6 +99,23 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    +    def list_objects(
    +        self,
    +        bucket: str,
    +        *,
    +        prefix: str = "",
    +        delimiter: str | None = None,
    +        max_keys: int = 1000,
    +        continuation_token: str | None = None,
    +    ) -> ListObjectsResult:
    +        with self._lock:
    +            return list_objects(
    +                self._bucket(bucket).records,
    +                prefix=prefix,
    +                delimiter=delimiter,
    +                max_keys=max_keys,
    +                continuation_token=continuation_token,
    +            )

         def list_object_versions(
             self, bucket: str, *, prefix: str = ""
    @@ -103,10 +123,8 @@ class MiniS3:
             with self._lock:
                 return list_object_versions(self._bucket(bucket).records, prefix=prefix)

    -
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
             except KeyError as exc:
                 raise NoSuchBucket(name) from exc
    -
    ```

**What it is and why it appears**

The service adds the public locked entry for current listing.

**Runtime role**

It supplies one consistent records snapshot and delegates all read-only projection rules to `listing.py`.

**Key code**

```python
with self._lock:
```

**Statement understanding**

Even a pure projection needs a stable input snapshot. The lock prevents a concurrent PUT or DELETE from changing keys halfway through pagination construction.

#### Public export wiring

Expose listing values while keeping all projection semantics in the core block.

??? note "Supporting file diffs (1 file)"
    **`src/minis3/__init__.py`**

    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index f9c1adf..1a69ac7 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -1,7 +1,43 @@
     """Public API for the MiniS3 teaching implementation."""
    -from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
    +
    +from .errors import (
    +    BucketAlreadyExists,
    +    BucketNotEmpty,
    +    InvalidContinuationToken,
    +    MiniS3Error,
    +    NoSuchBucket,
    +    NoSuchKey,
    +    NoSuchVersion,
    +)
     from .bucket import SequenceCounter, VersioningState
    +from .listing import (
    +    ListedObject,
    +    ListedVersion,
    +    ListObjectsResult,
    +    ListObjectVersionsResult,
    +)
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
     from .store import MiniS3
     from .storage import InjectedCrash
    -from .listing import ListedVersion, ListObjectVersionsResult
    +
    +__all__ = [
    +    "BucketAlreadyExists",
    +    "BucketNotEmpty",
    +    "DeleteMarker",
    +    "ListedObject",
    +    "ListedVersion",
    +    "ListObjectsResult",
    +    "ListObjectVersionsResult",
    +    "MiniS3",
    +    "InvalidContinuationToken",
    +    "InjectedCrash",
    +    "MiniS3Error",
    +    "NoSuchBucket",
    +    "NoSuchKey",
    +    "NoSuchVersion",
    +    "ObjectRecord",
    +    "SequenceCounter",
    +    "Version",
    +    "VersioningState",
    +    "content_etag",
    +]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/06-directory-illusion/tests.txt)`. The five new cases prove projection and token behavior while all earlier history tests remain cumulative.

### Durable takeaways

Keys stay flat; directories are a read-time illusion; contents and prefixes share page capacity; continuation tokens belong to one exact query.

### Explain it in your own words

MiniS3 produces directory-like listing by grouping flat strings at a delimiter. It never creates folders. Pagination operates on the combined projected result, and its opaque token is bound to the prefix and delimiter so it cannot be reused with different query semantics.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/04-listing.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-05...stage-06)

After finishing, use `git checkout stage-06` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/06-directory-illusion/stage.patch)
