# Stage 03 · Durable storage boundary

### Goal

Give Bucket state a durable representation with immutable artifacts and a publish-last manifest.

??? note "Deliverable files"
    - `src/minis3/storage/__init__.py`
    - `src/minis3/storage/atomic.py`
    - `src/minis3/storage/disk.py`
    - `tests/test_storage_boundary.py`

### The problem at this point

Stage 02 owns correct in-memory histories, but a process exit loses all of them. Writing one mutable JSON file directly is not enough: a crash can leave half a file or bytes whose directory entry was never made durable.

### Failure preview

The storage contract writes a bucket, creates a new `DiskStorage` over the same directory, and expects the exact body, ETag, version, and maximum sequence back. A missing fsync or publish order may pass an in-process read yet fail this restart observation.

### Basic concepts

Atomic visibility and durability are separate. `os.replace` makes readers observe either the old complete name or the new complete name. File `fsync` persists file bytes; parent-directory `fsync` persists the name change.

MiniS3 stores immutable data/metadata artifacts and a small mutable `manifest.json`. The manifest is the authority: only artifact IDs named by a successfully published manifest are visible after restart.

### Why this mechanism is necessary

Updating one large mutable state file makes every object write rewrite shared state and enlarges the crash surface. Immutable artifacts can be written safely first. Publishing their references last gives recovery one unambiguous commit record and lets it discard orphaned work.

### Runtime mental model

`DiskStorage.persist_bucket` writes every missing immutable artifact, then calls `atomic_write` for the manifest. `atomic_write` writes a temporary file, flushes and fsyncs it, replaces the final name, and fsyncs the parent. Startup loads only manifest references and cleans everything else.

### File-by-file walkthrough

#### `src/minis3/storage/atomic.py`

??? note "File diff: src/minis3/storage/atomic.py"
    ```diff
    diff --git a/src/minis3/storage/atomic.py b/src/minis3/storage/atomic.py
    new file mode 100644
    index 0000000..d7d741b
    --- /dev/null
    +++ b/src/minis3/storage/atomic.py
    @@ -0,0 +1,57 @@
    +"""Crash-safe file publication shared across the System-in-Miniature series.
    +
    +The recurring pattern is: write a temporary file, flush its bytes with fsync,
    +rename it atomically into place, then fsync the parent directory. Readers only
    +open the final name, so they observe the old complete file or the new complete
    +file, never a partially written file.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable
    +import os
    +from pathlib import Path
    +
    +
    +class InjectedCrash(RuntimeError):
    +    """A deliberate process-crash boundary used by tests and labs."""
    +
    +
    +CrashInjector = Callable[[str], None]
    +
    +
    +def fsync_directory(path: Path) -> None:
    +    """Persist directory-entry changes on POSIX filesystems."""
    +
    +    descriptor = os.open(path, os.O_RDONLY)
    +    try:
    +        os.fsync(descriptor)
    +    finally:
    +        os.close(descriptor)
    +
    +
    +def durable_mkdir(path: Path, *, parents: bool = True) -> None:
    +    """Create directories and persist every new entry in its parent."""
    +
    +    missing: list[Path] = []
    +    current = path
    +    while not current.exists():
    +        missing.append(current)
    +        current = current.parent
    +
    +    path.mkdir(parents=parents, exist_ok=True)
    +    for created in reversed(missing):
    +        fsync_directory(created.parent)
    +
    +
    +def atomic_write(path: Path, payload: bytes) -> None:
    +    """Publish one complete file using the series-wide crash-safe pattern."""
    +
    +    durable_mkdir(path.parent)
    +    temporary = path.with_name(path.name + ".tmp-write")
    +    with temporary.open("wb") as handle:
    +        handle.write(payload)
    +        handle.flush()
    +        os.fsync(handle.fileno())
    +    os.replace(temporary, path)
    +    fsync_directory(path.parent)
    ```

##### What it is and why it appears

This file owns reusable filesystem publication primitives rather than S3 domain decisions.

##### Runtime role

DiskStorage calls it whenever a file or directory entry must survive a crash. It is the lowest layer at which visibility and durability ordering can be inspected.

##### Key code

```python
os.replace(temporary, path)
fsync_directory(path.parent)
```

##### Statement understanding

Replace changes which complete file the final name refers to; the following directory fsync makes that rename durable. Reversing or omitting the second line can leave a rename visible now but absent after power loss.

#### `src/minis3/storage/disk.py`

??? note "File diff: src/minis3/storage/disk.py"
    ```diff
    diff --git a/src/minis3/storage/disk.py b/src/minis3/storage/disk.py
    new file mode 100644
    index 0000000..8ad143f
    --- /dev/null
    +++ b/src/minis3/storage/disk.py
    @@ -0,0 +1,227 @@
    +"""Disk layout, manifest publication, and startup recovery.
    +
    +Layout::
    +
    +    buckets/<encoded-bucket>/
    +      manifest.json
    +      objects/<sha256-key>/<storage-id>.json
    +      objects/<sha256-key>/<storage-id>.data
    +
    +Artifacts are immutable and written first. ``manifest.json`` is written last,
    +so its atomic rename is the visibility linearization point. Recovery trusts
    +only manifest references and removes temporary or orphaned artifacts.
    +"""
    +
    +from __future__ import annotations
    +
    +from base64 import urlsafe_b64encode
    +from collections.abc import Callable
    +from hashlib import sha256
    +import json
    +import os
    +from pathlib import Path
    +import shutil
    +
    +from ..bucket import Bucket, VersioningState
    +from ..model import DeleteMarker, ObjectRecord, ObjectVersion, Version
    +from .atomic import atomic_write, durable_mkdir, fsync_directory
    +
    +
    +def _encoded_name(name: str) -> str:
    +    if not name:
    +        raise ValueError("bucket name must not be empty")
    +    return urlsafe_b64encode(name.encode()).decode().rstrip("=")
    +
    +
    +def _object_directory(bucket_directory: Path, key: str) -> Path:
    +    return bucket_directory / "objects" / sha256(key.encode()).hexdigest()
    +
    +
    +class DiskStorage:
    +    """Own durable bucket directories and recover complete manifests."""
    +
    +    def __init__(
    +        self,
    +        root: str | Path,
    +        *,
    +        crash_injector: Callable[[str], None] | None = None,
    +    ) -> None:
    +        self.root = Path(root)
    +        self.buckets_root = self.root / "buckets"
    +        durable_mkdir(self.buckets_root)
    +        self._inject = crash_injector or (lambda _point: None)
    +
    +    def load_buckets(self) -> tuple[dict[str, Bucket], int]:
    +        """Recover published buckets and return the maximum used sequence."""
    +
    +        buckets: dict[str, Bucket] = {}
    +        maximum_sequence = 0
    +        for child in sorted(self.buckets_root.iterdir()):
    +            if child.name.startswith((".tmp-", ".deleted-")):
    +                shutil.rmtree(child)
    +                continue
    +            if not child.is_dir():
    +                continue
    +            manifest_path = child / "manifest.json"
    +            if not manifest_path.exists():
    +                shutil.rmtree(child)
    +                continue
    +            bucket = self._load_bucket(child)
    +            buckets[bucket.name] = bucket
    +            for record in bucket.records.values():
    +                for item in record.versions:
    +                    maximum_sequence = max(maximum_sequence, item.sequence)
    +            self._clean_bucket(child, bucket)
    +        fsync_directory(self.buckets_root)
    +        return buckets, maximum_sequence
    +
    +    def create_bucket(self, bucket: Bucket) -> None:
    +        """Atomically make a fully initialized bucket directory visible."""
    +
    +        final = self._bucket_directory(bucket.name)
    +        temporary = self.buckets_root / f".tmp-{final.name}"
    +        if temporary.exists():
    +            shutil.rmtree(temporary)
    +            fsync_directory(self.buckets_root)
    +        durable_mkdir(temporary, parents=False)
    +        durable_mkdir(temporary / "objects", parents=False)
    +        manifest = self._manifest_bytes(bucket)
    +        with (temporary / "manifest.json").open("wb") as handle:
    +            handle.write(manifest)
    +            handle.flush()
    +            os.fsync(handle.fileno())
    +        fsync_directory(temporary)
    +        os.replace(temporary, final)
    +        fsync_directory(self.buckets_root)
    +
    +    def delete_bucket(self, name: str) -> None:
    +        """Remove an empty bucket via a recoverable directory rename."""
    +
    +        source = self._bucket_directory(name)
    +        tombstone = self.buckets_root / f".deleted-{source.name}"
    +        os.replace(source, tombstone)
    +        fsync_directory(self.buckets_root)
    +        shutil.rmtree(tombstone)
    +        fsync_directory(self.buckets_root)
    +
    +    def persist_bucket(self, bucket: Bucket) -> None:
    +        """Write missing artifacts, then atomically publish their references."""
    +
    +        directory = self._bucket_directory(bucket.name)
    +        for record in bucket.records.values():
    +            for item in record.versions:
    +                self._write_artifact(directory, record.key, item)
    +
    +        # This hook models process death after durable artifacts but before the
    +        # only visibility-changing rename.
    +        self._inject("before_manifest_publish")
    +        atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
    +        self._inject("after_manifest_publish")
    +        self._clean_bucket(directory, bucket)
    +
    +    def _bucket_directory(self, name: str) -> Path:
    +        return self.buckets_root / _encoded_name(name)
    +
    +    def _manifest_bytes(self, bucket: Bucket) -> bytes:
    +        payload = {
    +            "format_version": 1,
    +            "name": bucket.name,
    +            "versioning": bucket.versioning.value,
    +            "records": {
    +                key: [item.storage_id for item in record.versions]
    +                for key, record in sorted(bucket.records.items())
    +            },
    +        }
    +        return json.dumps(
    +            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    +        ).encode()
    +
    +    def _write_artifact(
    +        self, bucket_directory: Path, key: str, item: ObjectVersion
    +    ) -> None:
    +        directory = _object_directory(bucket_directory, key)
    +        if not directory.exists():
    +            directory.mkdir()
    +            self._inject("after_object_directory_create")
    +            fsync_directory(directory.parent)
    +            self._inject("after_object_directory_parent_fsync")
    +        metadata_path = directory / f"{item.storage_id}.json"
    +        if metadata_path.exists():
    +            return
    +        metadata: dict[str, object] = {
    +            "key": key,
    +            "kind": "delete_marker" if isinstance(item, DeleteMarker) else "version",
    +            "version_id": item.version_id,
    +            "storage_id": item.storage_id,
    +            "sequence": item.sequence,
    +        }
    +        if isinstance(item, Version):
    +            atomic_write(directory / f"{item.storage_id}.data", item.body)
    +            metadata.update(etag=item.etag, size=item.size)
    +        atomic_write(
    +            metadata_path,
    +            json.dumps(
    +                metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    +            ).encode(),
    +        )
    +
    +    def _load_bucket(self, directory: Path) -> Bucket:
    +        manifest = json.loads((directory / "manifest.json").read_text())
    +        if manifest.get("format_version") != 1:
    +            raise ValueError(f"unsupported manifest in {directory}")
    +        bucket = Bucket(
    +            name=manifest["name"],
    +            versioning=VersioningState(manifest["versioning"]),
    +        )
    +        for key, storage_ids in manifest["records"].items():
    +            versions = tuple(
    +                self._load_artifact(directory, key, storage_id)
    +                for storage_id in storage_ids
    +            )
    +            bucket.records[key] = ObjectRecord(key, versions)
    +        return bucket
    +
    +    def _load_artifact(
    +        self, bucket_directory: Path, key: str, storage_id: str
    +    ) -> ObjectVersion:
    +        directory = _object_directory(bucket_directory, key)
    +        metadata = json.loads((directory / f"{storage_id}.json").read_text())
    +        if metadata["key"] != key or metadata["storage_id"] != storage_id:
    +            raise ValueError(f"artifact identity mismatch: {storage_id}")
    +        if metadata["kind"] == "delete_marker":
    +            return DeleteMarker(
    +                version_id=metadata["version_id"],
    +                storage_id=storage_id,
    +                sequence=metadata["sequence"],
    +            )
    +        body = (directory / f"{storage_id}.data").read_bytes()
    +        version = Version(
    +            version_id=metadata["version_id"],
    +            storage_id=storage_id,
    +            sequence=metadata["sequence"],
    +            body=body,
    +            etag=metadata["etag"],
    +        )
    +        if version.size != metadata["size"]:
    +            raise ValueError(f"artifact size mismatch: {storage_id}")
    +        return version
    +
    +    def _clean_bucket(self, directory: Path, bucket: Bucket) -> None:
    +        for temporary in directory.glob("*.tmp-*"):
    +            temporary.unlink()
    +        referenced = {
    +            item.storage_id
    +            for record in bucket.records.values()
    +            for item in record.versions
    +        }
    +        objects = directory / "objects"
    +        if not objects.exists():
    +            return
    +        for path in sorted(objects.rglob("*")):
    +            if path.is_file() and ".tmp-" in path.name:
    +                path.unlink()
    +            elif path.is_file() and path.stem not in referenced:
    +                path.unlink()
    +        for path in sorted(objects.rglob("*"), reverse=True):
    +            if path.is_dir() and not any(path.iterdir()):
    +                path.rmdir()
    ```

##### What it is and why it appears

This is the sole owner of disk layout, manifest publication, and restart recovery for buckets.

##### Runtime role

It translates Bucket histories into immutable `.data`/`.json` artifacts plus manifest references, and reconstructs Buckets on startup.

##### Key code

```python
self._inject("before_manifest_publish")
atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
self._inject("after_manifest_publish")
```

##### Statement understanding

The manifest write sits between two named crash points because it is the visibility boundary. Artifacts before it are harmless until referenced; after it, recovery must treat the new state as committed.

#### `src/minis3/storage/__init__.py`

??? note "File diff: src/minis3/storage/__init__.py"
    ```diff
    diff --git a/src/minis3/storage/__init__.py b/src/minis3/storage/__init__.py
    new file mode 100644
    index 0000000..673ad9e
    --- /dev/null
    +++ b/src/minis3/storage/__init__.py
    @@ -0,0 +1,7 @@
    +"""Durable storage boundary for manifest-based atomic publication."""
    +
    +from .atomic import InjectedCrash
    +from .disk import DiskStorage
    +
    +__all__ = ["DiskStorage", "InjectedCrash"]
    +
    ```

##### What it is and why it appears

This package boundary exports the durable adapter and the deliberate crash type used by later recovery experiments.

##### Runtime role

It provides stable imports while keeping layout helpers internal.

##### Statement understanding

Exporting `DiskStorage` names the storage owner; exporting `InjectedCrash` makes crash boundaries testable without exposing every helper.

#### `tests/test_storage_boundary.py`

??? note "File diff: tests/test_storage_boundary.py"
    ```diff
    diff --git a/tests/test_storage_boundary.py b/tests/test_storage_boundary.py
    new file mode 100644
    index 0000000..74c9d9e
    --- /dev/null
    +++ b/tests/test_storage_boundary.py
    @@ -0,0 +1,18 @@
    +"""Focused contract for manifest publication before service wiring."""
    +
    +from minis3.bucket import Bucket, SequenceCounter, VersioningState
    +from minis3.storage import DiskStorage
    +
    +
    +def test_disk_storage_publishes_and_recovers_one_complete_bucket(tmp_path) -> None:
    +    storage = DiskStorage(tmp_path)
    +    bucket = Bucket("b", versioning=VersioningState.ENABLED)
    +    version = bucket.put("key", b"value", SequenceCounter())
    +
    +    storage.create_bucket(Bucket("b"))
    +    storage.persist_bucket(bucket)
    +    recovered, maximum_sequence = DiskStorage(tmp_path).load_buckets()
    +
    +    assert recovered["b"].get("key") == version
    +    assert maximum_sequence == version.sequence
    +    assert not list(tmp_path.rglob("*.tmp-*"))
    ```

##### What it is and why it appears

This first storage contract proves one complete bucket can cross a process-like restart boundary.

##### Runtime role

It persists state, constructs a fresh adapter, and compares recovered values and sequence metadata. It is broader than a serialization unit test but narrower than the public MiniS3 service.

##### Key code

```python
recovered, maximum_sequence = DiskStorage(tmp_path).load_buckets()
```

##### Statement understanding

Using a new adapter is essential: reading the same in-memory Bucket would not prove bytes were published or recoverable. Returning `maximum` also prevents future sequence reuse.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`. It proves a clean publish/restart path. Stages 07 and 08 will separately prove crash points and directory-fsync cleanup.

### Durable takeaways

Rename provides atomic visibility; fsync provides durability; the manifest is the commit record; immutable artifacts are not visible merely because they exist.

### Explain it in your own words

MiniS3 writes immutable object artifacts first and atomically publishes a manifest last. Recovery trusts that manifest, so a crash can leave extra files but cannot expose a half-published object. The rename is the visibility point and parent fsync makes that decision survive restart.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-02...stage-03)

After finishing, use `git checkout stage-03` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/03-durable-storage-boundary/stage.patch)
