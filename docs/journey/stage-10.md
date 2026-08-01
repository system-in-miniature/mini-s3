# Stage 10 · Durable multipart staging

### Goal

Persist private multipart uploads and atomically replace parts without publishing an object.

??? note "Deliverable files"
    - `src/minis3/__init__.py`
    - `src/minis3/bucket.py`
    - `src/minis3/model.py`
    - `src/minis3/storage/disk.py`
    - `src/minis3/store.py`
    - `tests/test_multipart.py`

### The problem at this point

Stage 09 validates abstract staged parts, but a real client needs upload IDs and part bytes to survive retries and restarts. Those bytes must remain invisible to normal GET/List until completion publishes exactly one object.

### Failure preview

The first integration contract creates an upload for key `right`, then tries to upload through key `wrong` and through part numbers `0` and `10001`. Each request must fail before writing staging. Otherwise an upload ID can be confused across keys or create invalid part files.

### Basic concepts

Staging is durable private state, not a partially visible object. Each upload has identity `(bucket, key, upload_id)` and its own `parts/` directory. Re-uploading the same part number atomically replaces that staged slot.

The object model gains creation time and optional `multipart_upload_id` provenance for a future completed version. These fields do not make staging visible; only an `ObjectRecord` referenced by the Bucket manifest does that.

### Why this mechanism is necessary

Keeping parts only in memory makes retry and restart unreliable. Writing them directly into object history exposes incomplete values. A separate durable namespace preserves work while maintaining the one publication boundary established earlier.

### Runtime mental model

The service allocates a deterministic upload ID and asks DiskStorage to create `uploads/<id>/upload.json` plus `parts/`. `upload_part` validates the number and upload identity, then atomically writes one numbered `.data` file. Abort removes only that private upload directory.

### File-by-file walkthrough

#### `src/minis3/model.py`

##### What it is and why it appears

Versions and markers gain timestamps; data versions can record which multipart upload produced them after completion.

##### Runtime role

Lifecycle and recovery will consume these fields later. They remain immutable metadata attached to published history.

##### Key code

```python
multipart_upload_id: str | None = None
```

##### Statement understanding

`None` identifies normal PUTs; a completed multipart version can retain provenance without turning the upload itself into visible history.

??? note "File diff: src/minis3/model.py"
    ```diff
    diff --git a/src/minis3/model.py b/src/minis3/model.py
    index da662fc..7375afd 100644
    --- a/src/minis3/model.py
    +++ b/src/minis3/model.py
    @@ -36,6 +36,8 @@ class Version:
         sequence: int
         body: bytes
         etag: str
    +    created_at: float = 0.0
    +    multipart_upload_id: str | None = None

         @property
         def size(self) -> int:
    @@ -57,6 +59,7 @@ class DeleteMarker:
         version_id: str
         storage_id: str
         sequence: int
    +    created_at: float = 0.0

         @property
         def is_delete_marker(self) -> bool:
    @@ -72,4 +75,3 @@ class ObjectRecord:

         key: str
         versions: tuple[ObjectVersion, ...] = ()
    -
    ```

#### `src/minis3/bucket.py`

##### What it is and why it appears

Bucket PUT accepts an optional externally calculated ETag, timestamp, and multipart provenance while keeping normal PUT defaults.

##### Runtime role

Completion will reuse the same version transition rather than inventing a second publication path.

##### Key code

```python
etag=content_etag(body) if etag is None else etag,
```

##### Statement understanding

Normal PUT still derives a whole-body ETag; multipart completion can supply its validated composite ETag. Recomputing it from assembled bytes would be wrong.

??? note "File diff: src/minis3/bucket.py"
    ```diff
    diff --git a/src/minis3/bucket.py b/src/minis3/bucket.py
    index b0a46e5..cc695a1 100644
    --- a/src/minis3/bucket.py
    +++ b/src/minis3/bucket.py
    @@ -69,7 +69,16 @@ class Bucket:
                 raise ValueError("versioning must be enabled before it can be suspended")
             self.versioning = state

    -    def put(self, key: str, body: bytes, next_sequence: Callable[[], int]) -> Version:
    +    def put(
    +        self,
    +        key: str,
    +        body: bytes,
    +        next_sequence: Callable[[], int],
    +        *,
    +        etag: str | None = None,
    +        now: float = 0.0,
    +        multipart_upload_id: str | None = None,
    +    ) -> Version:
             sequence = next_sequence()
             version_id = (
                 f"v{sequence:08d}"
    @@ -81,7 +90,9 @@ class Bucket:
                 storage_id=f"e{sequence:08d}",
                 sequence=sequence,
                 body=bytes(body),
    -            etag=content_etag(body),
    +            etag=content_etag(body) if etag is None else etag,
    +            created_at=now,
    +            multipart_upload_id=multipart_upload_id,
             )
             old = self.records.get(key, ObjectRecord(key))

    @@ -120,6 +131,8 @@ class Bucket:
             key: str,
             next_sequence: Callable[[], int],
             version_id: str | None = None,
    +        *,
    +        now: float = 0.0,
         ) -> ObjectVersion | None:
             record = self.records.get(key)

    @@ -149,7 +162,9 @@ class Bucket:
                 if self.versioning is VersioningState.ENABLED
                 else NULL_VERSION_ID
             )
    -        marker = DeleteMarker(marker_id, f"e{sequence:08d}", sequence)
    +        marker = DeleteMarker(
    +            marker_id, f"e{sequence:08d}", sequence, created_at=now
    +        )
             old_versions = () if record is None else record.versions
             if self.versioning is VersioningState.SUSPENDED or has_named_history:
                 old_versions = tuple(
    ```

#### `src/minis3/storage/disk.py`

##### What it is and why it appears

DiskStorage gains the private upload layout, atomic part writes, identity validation, removal, and restart recovery.

##### Runtime role

It owns durable staging just as it owns durable object artifacts, but normal manifest/list code never consults `uploads/`.

##### Key code

```python
atomic_write(directory / "parts" / f"{part.part_number:05d}.data", part.body)
```

##### Statement understanding

The part number selects one stable filename and `atomic_write` replaces it completely. A retry cannot leave half old and half new bytes.

??? note "File diff: src/minis3/storage/disk.py"
    ```diff
    diff --git a/src/minis3/storage/disk.py b/src/minis3/storage/disk.py
    index 8ad143f..95b160f 100644
    --- a/src/minis3/storage/disk.py
    +++ b/src/minis3/storage/disk.py
    @@ -23,7 +23,9 @@ from pathlib import Path
     import shutil

     from ..bucket import Bucket, VersioningState
    +from ..errors import NoSuchUpload
     from ..model import DeleteMarker, ObjectRecord, ObjectVersion, Version
    +from ..multipart import MultipartUpload, StagedPart
     from .atomic import atomic_write, durable_mkdir, fsync_directory


    @@ -72,6 +74,9 @@ class DiskStorage:
                     for item in record.versions:
                         maximum_sequence = max(maximum_sequence, item.sequence)
                 self._clean_bucket(child, bucket)
    +            maximum_sequence = max(
    +                maximum_sequence, self._recover_uploads(child, bucket)
    +            )
             fsync_directory(self.buckets_root)
             return buckets, maximum_sequence

    @@ -85,6 +90,7 @@ class DiskStorage:
                 fsync_directory(self.buckets_root)
             durable_mkdir(temporary, parents=False)
             durable_mkdir(temporary / "objects", parents=False)
    +        durable_mkdir(temporary / "uploads", parents=False)
             manifest = self._manifest_bytes(bucket)
             with (temporary / "manifest.json").open("wb") as handle:
                 handle.write(manifest)
    @@ -119,9 +125,108 @@ class DiskStorage:
             self._inject("after_manifest_publish")
             self._clean_bucket(directory, bucket)

    +    def create_multipart_upload(self, upload: MultipartUpload) -> None:
    +        """Durably create private staging that no object listing consults."""
    +
    +        bucket_directory = self._bucket_directory(upload.bucket)
    +        uploads = bucket_directory / "uploads"
    +        durable_mkdir(uploads)
    +        directory = self._upload_directory(bucket_directory, upload.upload_id)
    +        durable_mkdir(directory, parents=False)
    +        durable_mkdir(directory / "parts", parents=False)
    +        metadata = {
    +            "format_version": 1,
    +            "bucket": upload.bucket,
    +            "key": upload.key,
    +            "upload_id": upload.upload_id,
    +            "sequence": upload.sequence,
    +            "initiated_at": upload.initiated_at,
    +        }
    +        atomic_write(
    +            directory / "upload.json",
    +            json.dumps(
    +                metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    +            ).encode(),
    +        )
    +
    +    def write_multipart_part(
    +        self,
    +        bucket: str,
    +        key: str,
    +        upload_id: str,
    +        part: StagedPart,
    +    ) -> None:
    +        """Atomically add or replace one durable staged part."""
    +
    +        self.load_multipart_upload(bucket, key, upload_id)
    +        directory = self._upload_directory(
    +            self._bucket_directory(bucket), upload_id
    +        )
    +        atomic_write(directory / "parts" / f"{part.part_number:05d}.data", part.body)
    +
    +    def load_multipart_upload(
    +        self, bucket: str, key: str, upload_id: str
    +    ) -> tuple[MultipartUpload, dict[int, StagedPart]]:
    +        """Reload one upload and all completely published part files."""
    +
    +        directory = self._upload_directory(
    +            self._bucket_directory(bucket), upload_id
    +        )
    +        metadata_path = directory / "upload.json"
    +        if not metadata_path.exists():
    +            raise NoSuchUpload(upload_id)
    +        metadata = json.loads(metadata_path.read_text())
    +        if (
    +            metadata.get("format_version") != 1
    +            or metadata.get("bucket") != bucket
    +            or metadata.get("key") != key
    +            or metadata.get("upload_id") != upload_id
    +        ):
    +            raise NoSuchUpload(upload_id)
    +        upload = MultipartUpload(
    +            bucket=metadata["bucket"],
    +            key=metadata["key"],
    +            upload_id=metadata["upload_id"],
    +            sequence=metadata["sequence"],
    +            initiated_at=metadata["initiated_at"],
    +        )
    +        parts: dict[int, StagedPart] = {}
    +        for path in sorted((directory / "parts").glob("*.data")):
    +            try:
    +                part_number = int(path.stem)
    +            except ValueError:
    +                continue
    +            parts[part_number] = StagedPart(part_number, path.read_bytes())
    +        return upload, parts
    +
    +    def remove_multipart_upload(
    +        self, bucket: str, key: str, upload_id: str
    +    ) -> None:
    +        """Remove staging through a rename so partial deletion is recoverable."""
    +
    +        self.load_multipart_upload(bucket, key, upload_id)
    +        bucket_directory = self._bucket_directory(bucket)
    +        source = self._upload_directory(bucket_directory, upload_id)
    +        tombstone = source.with_name(f".deleted-{upload_id}")
    +        os.replace(source, tombstone)
    +        fsync_directory(tombstone.parent)
    +        shutil.rmtree(tombstone)
    +        fsync_directory(tombstone.parent)
    +
         def _bucket_directory(self, name: str) -> Path:
             return self.buckets_root / _encoded_name(name)

    +    def _upload_directory(
    +        self, bucket_directory: Path, upload_id: str
    +    ) -> Path:
    +        if (
    +            not upload_id.startswith("u")
    +            or not upload_id[1:].isdigit()
    +            or len(upload_id) != 9
    +        ):
    +            raise NoSuchUpload(upload_id)
    +        return bucket_directory / "uploads" / upload_id
    +
         def _manifest_bytes(self, bucket: Bucket) -> bytes:
             payload = {
                 "format_version": 1,
    @@ -154,10 +259,15 @@ class DiskStorage:
                 "version_id": item.version_id,
                 "storage_id": item.storage_id,
                 "sequence": item.sequence,
    +            "created_at": item.created_at,
             }
             if isinstance(item, Version):
                 atomic_write(directory / f"{item.storage_id}.data", item.body)
    -            metadata.update(etag=item.etag, size=item.size)
    +            metadata.update(
    +                etag=item.etag,
    +                size=item.size,
    +                multipart_upload_id=item.multipart_upload_id,
    +            )
             atomic_write(
                 metadata_path,
                 json.dumps(
    @@ -193,6 +303,7 @@ class DiskStorage:
                     version_id=metadata["version_id"],
                     storage_id=storage_id,
                     sequence=metadata["sequence"],
    +                created_at=metadata.get("created_at", 0.0),
                 )
             body = (directory / f"{storage_id}.data").read_bytes()
             version = Version(
    @@ -201,6 +312,8 @@ class DiskStorage:
                 sequence=metadata["sequence"],
                 body=body,
                 etag=metadata["etag"],
    +            created_at=metadata.get("created_at", 0.0),
    +            multipart_upload_id=metadata.get("multipart_upload_id"),
             )
             if version.size != metadata["size"]:
                 raise ValueError(f"artifact size mismatch: {storage_id}")
    @@ -225,3 +338,42 @@ class DiskStorage:
             for path in sorted(objects.rglob("*"), reverse=True):
                 if path.is_dir() and not any(path.iterdir()):
                     path.rmdir()
    +
    +    def _recover_uploads(self, directory: Path, bucket: Bucket) -> int:
    +        """Remove completed/torn staging and return its largest sequence."""
    +
    +        uploads = directory / "uploads"
    +        durable_mkdir(uploads)
    +        completed = {
    +            item.multipart_upload_id
    +            for record in bucket.records.values()
    +            for item in record.versions
    +            if isinstance(item, Version) and item.multipart_upload_id is not None
    +        }
    +        maximum_sequence = 0
    +        changed = False
    +        for child in sorted(uploads.iterdir()):
    +            if child.name.startswith((".tmp-", ".deleted-")):
    +                shutil.rmtree(child)
    +                changed = True
    +                continue
    +            metadata_path = child / "upload.json"
    +            if not child.is_dir() or not metadata_path.exists():
    +                if child.is_dir():
    +                    shutil.rmtree(child)
    +                else:
    +                    child.unlink()
    +                changed = True
    +                continue
    +            metadata = json.loads(metadata_path.read_text())
    +            maximum_sequence = max(maximum_sequence, metadata["sequence"])
    +            if child.name in completed:
    +                shutil.rmtree(child)
    +                changed = True
    +                continue
    +            for temporary in child.rglob("*.tmp-*"):
    +                temporary.unlink()
    +                changed = True
    +        if changed:
    +            fsync_directory(uploads)
    +        return maximum_sequence
    ```

#### `src/minis3/store.py`

##### What it is and why it appears

The public service adds initiate, upload-part, and abort orchestration with an injectable clock and minimum part size.

##### Runtime role

It validates public parameters under the same lock, allocates deterministic upload identity, and delegates private bytes to DiskStorage.

##### Key code

```python
upload_id=f"u{sequence:08d}",
```

##### Statement understanding

Upload IDs share the monotonic sequence discipline, making restart recovery and teaching traces deterministic instead of relying on random UUIDs.

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index 7c82b41..0d7e596 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -1,9 +1,4 @@
    -"""Public service facade joining buckets, object state, and list projections.
    -
    -This initial service boundary deliberately resembles an SDK rather than an HTTP
    -server. A future thin protocol adapter can translate these domain values and
    -errors without taking ownership of storage semantics.
    -"""
    +"""Public service facade joining buckets, object state, and list projections."""

     from __future__ import annotations

    @@ -11,16 +6,21 @@ from collections.abc import Callable
     from copy import deepcopy
     from pathlib import Path
     from threading import RLock
    +from time import time

     from .bucket import Bucket, SequenceCounter, VersioningState
     from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    -from .listing import (
    -    ListObjectsResult,
    -    ListObjectVersionsResult,
    -    list_object_versions,
    -    list_objects,
    -)
    +from .listing import ListObjectsResult, ListObjectVersionsResult, list_object_versions, list_objects
     from .model import ObjectVersion, Version
    +from .multipart import (
    +    MAX_PART_NUMBER,
    +    MIN_PART_SIZE,
    +    CompletionEntry,
    +    MultipartPart,
    +    MultipartUpload,
    +    StagedPart,
    +    validate_completion,
    +)
     from .storage import DiskStorage


    @@ -33,9 +33,15 @@ class MiniS3:
             *,
             counter: Callable[[], int] | None = None,
             crash_injector: Callable[[str], None] | None = None,
    +        clock: Callable[[], float] | None = None,
    +        minimum_part_size: int = MIN_PART_SIZE,
         ) -> None:
    +        if minimum_part_size < 1:
    +            raise ValueError("minimum_part_size must be positive")
             self.root = Path(root)
             self._counter = counter or SequenceCounter()
    +        self._clock = clock or time
    +        self.minimum_part_size = minimum_part_size
             self._storage = DiskStorage(root, crash_injector=crash_injector)
             self._buckets, maximum_sequence = self._storage.load_buckets()
             ensure = getattr(self._counter, "ensure_at_least", None)
    @@ -43,6 +49,7 @@ class MiniS3:
                 ensure(maximum_sequence + 1)
             self._lock = RLock()

    +
         def create_bucket(self, name: str) -> None:
             with self._lock:
                 if name in self._buckets:
    @@ -51,6 +58,7 @@ class MiniS3:
                 self._storage.create_bucket(bucket)
                 self._buckets[name] = bucket

    +
         def delete_bucket(self, name: str) -> None:
             with self._lock:
                 bucket = self._bucket(name)
    @@ -59,6 +67,7 @@ class MiniS3:
                 self._storage.delete_bucket(name)
                 del self._buckets[name]

    +
         def set_bucket_versioning(
             self, name: str, state: VersioningState | str
         ) -> None:
    @@ -68,6 +77,7 @@ class MiniS3:
                 self._storage.persist_bucket(candidate)
                 self._buckets[name] = candidate

    +
         def put_object(self, bucket: str, key: str, body: bytes) -> Version:
             with self._lock:
                 candidate = deepcopy(self._bucket(bucket))
    @@ -76,12 +86,14 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    +
         def get_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> Version:
             with self._lock:
                 return self._bucket(bucket).get(key, version_id)

    +
         def head_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> Version:
    @@ -89,6 +101,7 @@ class MiniS3:

             return self.get_object(bucket, key, version_id=version_id)

    +
         def delete_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> ObjectVersion | None:
    @@ -99,6 +112,7 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    +
         def list_objects(
             self,
             bucket: str,
    @@ -117,14 +131,65 @@ class MiniS3:
                     continuation_token=continuation_token,
                 )

    +
         def list_object_versions(
             self, bucket: str, *, prefix: str = ""
         ) -> ListObjectVersionsResult:
             with self._lock:
                 return list_object_versions(self._bucket(bucket).records, prefix=prefix)

    +
    +    def create_multipart_upload(
    +        self, bucket: str, key: str
    +    ) -> MultipartUpload:
    +        """Initiate durable staging without adding a visible object record."""
    +
    +        with self._lock:
    +            self._bucket(bucket)
    +            sequence = self._counter()
    +            upload = MultipartUpload(
    +                bucket=bucket,
    +                key=key,
    +                upload_id=f"u{sequence:08d}",
    +                sequence=sequence,
    +                initiated_at=self._clock(),
    +            )
    +            self._storage.create_multipart_upload(upload)
    +            return upload
    +
    +
    +    def upload_part(
    +        self,
    +        bucket: str,
    +        key: str,
    +        upload_id: str,
    +        part_number: int,
    +        body: bytes,
    +    ) -> MultipartPart:
    +        """Durably add/replace a part; final-part size is decided at complete."""
    +
    +        if not 1 <= part_number <= MAX_PART_NUMBER:
    +            raise ValueError(f"part_number must be between 1 and {MAX_PART_NUMBER}")
    +        with self._lock:
    +            self._bucket(bucket)
    +            part = StagedPart(part_number, bytes(body))
    +            self._storage.write_multipart_part(bucket, key, upload_id, part)
    +            return part.receipt
    +
    +
    +    def abort_multipart_upload(
    +        self, bucket: str, key: str, upload_id: str
    +    ) -> None:
    +        """Discard one incomplete upload without affecting any object."""
    +
    +        with self._lock:
    +            self._bucket(bucket)
    +            self._storage.remove_multipart_upload(bucket, key, upload_id)
    +
    +
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
             except KeyError as exc:
                 raise NoSuchBucket(name) from exc
    +
    ```

#### `src/minis3/__init__.py`

##### What it is and why it appears

Multipart values and failures join the supported package API.

##### Runtime role

Callers can hold upload receipts and catch `NoSuchUpload` without importing storage internals.

##### Statement understanding

The exports expose domain contracts, not the private disk layout.

??? note "File diff: src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 1a69ac7..0c23aea 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -1,43 +1,9 @@
     """Public API for the MiniS3 teaching implementation."""
    -
    -from .errors import (
    -    BucketAlreadyExists,
    -    BucketNotEmpty,
    -    InvalidContinuationToken,
    -    MiniS3Error,
    -    NoSuchBucket,
    -    NoSuchKey,
    -    NoSuchVersion,
    -)
    +from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
     from .bucket import SequenceCounter, VersioningState
    -from .listing import (
    -    ListedObject,
    -    ListedVersion,
    -    ListObjectsResult,
    -    ListObjectVersionsResult,
    -)
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
     from .store import MiniS3
     from .storage import InjectedCrash
    -
    -__all__ = [
    -    "BucketAlreadyExists",
    -    "BucketNotEmpty",
    -    "DeleteMarker",
    -    "ListedObject",
    -    "ListedVersion",
    -    "ListObjectsResult",
    -    "ListObjectVersionsResult",
    -    "MiniS3",
    -    "InvalidContinuationToken",
    -    "InjectedCrash",
    -    "MiniS3Error",
    -    "NoSuchBucket",
    -    "NoSuchKey",
    -    "NoSuchVersion",
    -    "ObjectRecord",
    -    "SequenceCounter",
    -    "Version",
    -    "VersioningState",
    -    "content_etag",
    -]
    +from .listing import ListedObject, ListedVersion, ListObjectsResult, ListObjectVersionsResult
    +from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder, NoSuchUpload
    +from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
    ```

#### `tests/test_multipart.py`

##### What it is and why it appears

The first durable multipart test locks upload identity and legal part-number range.

##### Runtime role

It enters through `MiniS3`, so failures cover service validation plus storage identity lookup.

##### Key code

```python
store.upload_part("b", "wrong", upload.upload_id, 1, b"x")
```

##### Statement understanding

An upload ID is not globally interchangeable: the addressed Bucket and Key must match its persisted metadata before any part is written.

??? note "File diff: tests/test_multipart.py"
    ```diff
    diff --git a/tests/test_multipart.py b/tests/test_multipart.py
    new file mode 100644
    index 0000000..0b61034
    --- /dev/null
    +++ b/tests/test_multipart.py
    @@ -0,0 +1,30 @@
    +"""Multipart tests pin invisible staging and S3's composite ETag trap."""
    +
    +from hashlib import md5
    +from pathlib import Path
    +
    +import pytest
    +
    +from minis3 import (
    +    EntityTooSmall,
    +    InvalidPart,
    +    InvalidPartOrder,
    +    MiniS3,
    +    NoSuchKey,
    +    NoSuchUpload,
    +    SequenceCounter,
    +    content_etag,
    +)
    +
    +
    +def test_upload_identity_and_part_number_are_validated(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    upload = store.create_multipart_upload("b", "right")
    +
    +    with pytest.raises(NoSuchUpload):
    +        store.upload_part("b", "wrong", upload.upload_id, 1, b"x")
    +    with pytest.raises(ValueError):
    +        store.upload_part("b", "right", upload.upload_id, 0, b"x")
    +    with pytest.raises(ValueError):
    +        store.upload_part("b", "right", upload.upload_id, 10_001, b"x")
    ```

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/10-multipart-staging/tests.txt)`. It proves identity and range rejection while cumulative tests protect earlier object behavior. Completion visibility is deliberately deferred.

### Durable takeaways

Staging is durable but private; upload identity includes Bucket and Key; same-number retries replace atomically; only Bucket manifest publication creates an object.

### Explain it in your own words

MiniS3 stores incomplete multipart work in a separate durable namespace. The service validates upload identity and part numbers, while DiskStorage atomically replaces numbered part files. Normal GET and List remain unchanged because no ObjectRecord is published yet.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-09...stage-10)

After finishing, use `git checkout stage-10` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/10-multipart-staging/stage.patch)
