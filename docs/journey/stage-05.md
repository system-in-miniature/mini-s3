# Stage 05 · Version history projection

### Goal

Project complete histories without collapsing null versions, named versions, and delete markers.

??? note "Deliverable files"
    - `src/minis3/__init__.py`
    - `src/minis3/listing.py`
    - `src/minis3/store.py`
    - `tests/test_versioning.py`

### The problem at this point

GET returns one addressed data version, so it cannot explain the history hidden behind the latest value or marker. Administrative and recovery views need every retained entry plus enough metadata to distinguish their meanings.

### Failure preview

The suspended-delete contract creates named history, writes a `null` value, then deletes without a version ID. The expected history contains a new `null` marker and the older named versions, but not the replaced `null` data. A flat “all values” list would report the wrong state.

??? note "File diff: tests/test_versioning.py"
    ```diff
    diff --git a/tests/test_versioning.py b/tests/test_versioning.py
    index 389e45d..3f305c6 100644
    --- a/tests/test_versioning.py
    +++ b/tests/test_versioning.py
    @@ -1,8 +1,17 @@
     """Versioning is the central state-machine contract of M1."""

     from pathlib import Path
    +
     import pytest
    -from minis3 import BucketNotEmpty, MiniS3, NoSuchKey, NoSuchVersion, SequenceCounter, VersioningState
    +
    +from minis3 import (
    +    BucketNotEmpty,
    +    MiniS3,
    +    NoSuchKey,
    +    NoSuchVersion,
    +    SequenceCounter,
    +    VersioningState,
    +)
     from minis3.bucket import Bucket


    @@ -47,6 +56,22 @@ def test_unversioned_delete_defensively_preserves_named_history() -> None:
         assert bucket.get("k", historical.version_id) == historical


    +def test_unversioned_put_replaces_null_and_delete_removes_it(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter())
    +    store.create_bucket("photos")
    +
    +    first = store.put_object("photos", "cat.jpg", b"first")
    +    second = store.put_object("photos", "cat.jpg", b"second")
    +
    +    assert first.version_id == second.version_id == "null"
    +    assert store.get_object("photos", "cat.jpg").body == b"second"
    +    assert len(store.list_object_versions("photos").versions) == 1
    +
    +    assert store.delete_object("photos", "cat.jpg") is None
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("photos", "cat.jpg")
    +
    +
     def test_enabled_puts_stack_and_delete_marker_hides_history(tmp_path: Path) -> None:
         store = MiniS3(tmp_path, counter=SequenceCounter())
         store.create_bucket("photos")
    @@ -87,6 +112,28 @@ def test_specific_delete_removes_only_addressed_version(tmp_path: Path) -> None:
             store.get_object("b", "k", version_id=new.version_id)


    +def test_suspended_put_replaces_null_but_preserves_named_history(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter())
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    historical = store.put_object("b", "k", b"historical")
    +    store.set_bucket_versioning("b", "suspended")
    +
    +    first_null = store.put_object("b", "k", b"null-one")
    +    second_null = store.put_object("b", "k", b"null-two")
    +
    +    assert first_null.version_id == second_null.version_id == "null"
    +    assert store.get_object("b", "k").body == b"null-two"
    +    assert store.get_object(
    +        "b", "k", version_id=historical.version_id
    +    ).body == b"historical"
    +    assert [
    +        item.version_id for item in store.list_object_versions("b").versions
    +    ] == ["null", historical.version_id]
    +
    +
     def test_latest_marker_is_404_even_when_older_data_exists(tmp_path: Path) -> None:
         store = MiniS3(tmp_path)
         store.create_bucket("b")
    @@ -101,6 +148,24 @@ def test_latest_marker_is_404_even_when_older_data_exists(tmp_path: Path) -> Non
         assert store.get_object("b", "k").body == b"still here"


    +def test_suspended_delete_replaces_null_with_null_marker(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    historical = store.put_object("b", "k", b"named")
    +    store.set_bucket_versioning("b", "suspended")
    +    store.put_object("b", "k", b"replaceable null")
    +
    +    marker = store.delete_object("b", "k")
    +
    +    assert marker is not None and marker.version_id == "null"
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("b", "k")
    +    assert store.get_object(
    +        "b", "k", version_id=historical.version_id
    +    ).body == b"named"
    +
    +
     def test_nonempty_bucket_cannot_be_deleted(tmp_path: Path) -> None:
         store = MiniS3(tmp_path)
         store.create_bucket("b")
    ```

**What this test locks**

Three new scenarios lock the projection of unversioned replacement, suspended replacement, and suspended deletion.

**How it constructs the counterexample**

They observe public histories after real service mutations, so the evidence covers Bucket plus projection rather than a fabricated input alone.

**Key test statement**

```python
assert marker is not None and marker.version_id == "null"
```

**What a failure means**

Suspension does not mean deletion becomes physical. The new marker occupies the public `null` slot while named history remains addressable.

### Basic concepts

A projection is a read-only shape derived from owned state. `ListedVersion` does not become a second history owner; it converts each `Version` or `DeleteMarker` into fields useful to callers. `is_latest` depends on position within one key's newest-first tuple, not on the highest ID string globally.

### Why this mechanism is necessary

Returning raw internal objects would couple callers to storage fields and tempt them to mutate history. Returning only current data would erase markers and noncurrent versions. An explicit projection preserves semantics while keeping the aggregate authoritative.

### Runtime mental model

The service locks and passes Bucket records to `list_object_versions`. The pure function filters exact key prefixes, iterates keys deterministically, flattens each newest-first history, marks only index zero as latest, and returns an immutable result.

### Mechanism blocks

#### Version-history projection

Project newest-first Bucket histories into stable public values without losing null versions or delete markers.

??? note "File diff: src/minis3/listing.py"
    ```diff
    diff --git a/src/minis3/listing.py b/src/minis3/listing.py
    new file mode 100644
    index 0000000..3c40e0d
    --- /dev/null
    +++ b/src/minis3/listing.py
    @@ -0,0 +1,55 @@
    +"""Version-history projection over MiniS3 records."""
    +
    +
    +from __future__ import annotations
    +
    +
    +from dataclasses import dataclass
    +
    +
    +from .model import ObjectRecord, Version
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ListedVersion:
    +    """One data version or delete marker in a flattened history."""
    +
    +    key: str
    +    version_id: str
    +    is_latest: bool
    +    is_delete_marker: bool
    +    etag: str | None
    +    size: int | None
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ListObjectVersionsResult:
    +    """All retained versions and markers, ordered by key then newest first."""
    +
    +    versions: tuple[ListedVersion, ...]
    +
    +
    +def list_object_versions(
    +    records: dict[str, ObjectRecord],
    +    *,
    +    prefix: str = "",
    +) -> ListObjectVersionsResult:
    +    """Flatten complete histories without hiding delete markers."""
    +
    +    result: list[ListedVersion] = []
    +    for key in sorted(records):
    +        if not key.startswith(prefix):
    +            continue
    +        for index, item in enumerate(records[key].versions):
    +            is_data = isinstance(item, Version)
    +            result.append(
    +                ListedVersion(
    +                    key=key,
    +                    version_id=item.version_id,
    +                    is_latest=index == 0,
    +                    is_delete_marker=not is_data,
    +                    etag=item.etag if is_data else None,
    +                    size=item.size if is_data else None,
    +                )
    +            )
    +    return ListObjectVersionsResult(tuple(result))
    ```

**What it is and why it appears**

This read-side module introduces response values and the pure history projection.

**Runtime role**

It consumes records without mutation and emits a stable sequence carrying key, IDs, ETag/size when data exists, marker flag, and latest flag.

**Key code**

```python
etag=item.etag if is_data else None,
```

**Statement understanding**

A marker has no body-derived ETag. Making the field explicitly `None` preserves the distinction instead of inventing an empty-object fingerprint.

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index 5d418b8..23ddd8e 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -9,6 +9,7 @@ from threading import RLock

     from .bucket import Bucket, SequenceCounter, VersioningState
     from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    +from .listing import ListObjectVersionsResult, list_object_versions
     from .model import ObjectVersion, Version
     from .storage import DiskStorage

    @@ -96,6 +97,13 @@ class MiniS3:
                 return result


    +    def list_object_versions(
    +        self, bucket: str, *, prefix: str = ""
    +    ) -> ListObjectVersionsResult:
    +        with self._lock:
    +            return list_object_versions(self._bucket(bucket).records, prefix=prefix)
    +
    +
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
    ```

**What it is and why it appears**

The public service gains a locked read method for the new projection.

**Runtime role**

It resolves the Bucket and delegates to the pure listing function while preventing a concurrent mutation from changing the snapshot mid-read.

**Key code**

```python
return list_object_versions(self._bucket(bucket).records, prefix=prefix)
```

**Statement understanding**

The service passes records but does not reproduce projection logic. This keeps ownership clear and makes the pure function independently understandable.

#### Public export wiring

Expose the projection result types; their behavior is owned by the projection block above.

??? note "Supporting file diffs (1 file)"
    **`src/minis3/__init__.py`**

    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 11378e1..f9c1adf 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -4,3 +4,4 @@ from .bucket import SequenceCounter, VersioningState
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
     from .store import MiniS3
     from .storage import InjectedCrash
    +from .listing import ListedVersion, ListObjectVersionsResult
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`. The cumulative suite proves projection semantics across versioning states; current-object pagination belongs to Stage 06.

### Durable takeaways

A read projection explains state without owning it. Null data, named data, and markers remain distinct, and “latest” is local to each exact key history.

### Explain it in your own words

Version listing is a pure view over Bucket-owned history. It preserves entries that GET intentionally hides, marks the head of each key as latest, and keeps marker-only fields empty so callers can reconstruct what happened without mutating the source state.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-04...stage-05)

After finishing, use `git checkout stage-05` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/05-version-history/stage.patch)
