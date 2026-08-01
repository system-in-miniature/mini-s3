# Stage 03 · 持久化存储边界

### 目标

让 Bucket 通过单一存储所有者拥有持久 manifest 与不可变对象制品。

### 动手任务

从stage-02开始，实现 `DiskStorage`、`atomic_write`、`durable_mkdir` 与面向恢复的路径辅助函数。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/storage/__init__.py`
- `src/minis3/storage/atomic.py`
- `src/minis3/storage/disk.py`

### 机制走读

#### 所有权与数据流

`DiskStorage` 先写不可变数据与元数据 Artifact，最后发布 `manifest.json`；`atomic_write` 让 rename 成为可见性点，fsync 让目录项持久化。

#### 失败与排查

按 Artifact 路径、临时名、rename、父目录 fsync 的顺序追踪；重启时对照 Manifest 引用与恢复文件，未引用 Artifact 不能变得可见。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/storage/__init__.py`

存储适配器边界导出。

在领域变更后调用；把内存状态变成持久 Artifact，并在启动时重建。

**变化锚点:** 配置、导出或文档变化

??? note "文件差异：src/minis3/storage/__init__.py"
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

#### `src/minis3/storage/atomic.py`

可复用的 write/fsync/rename 持久性原语。

在领域变更后调用；把内存状态变成持久 Artifact，并在启动时重建。

**变化锚点:** `InjectedCrash`, `fsync_directory`, `durable_mkdir`, `atomic_write`

??? note "文件差异：src/minis3/storage/atomic.py"
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

#### `src/minis3/storage/disk.py`

磁盘布局、发布与恢复的所有者。

在领域变更后调用；把内存状态变成持久 Artifact，并在启动时重建。

**变化锚点:** `_encoded_name`, `_object_directory`, `DiskStorage`, `__init__`, `load_buckets`, `create_bucket`, `delete_bucket`, `persist_bucket`, `_bucket_directory`, `_manifest_bytes`, `_write_artifact`, `_load_bucket`, `_load_artifact`, `_clean_bucket`

??? note "文件差异：src/minis3/storage/disk.py"
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

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        manifest 引用可见的不可变制品；发布顺序决定可见性。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`

### 对应真实 S3 的一课

manifest 引用可见的不可变制品；发布顺序决定可见性。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-02...stage-03)

完成后可运行 `git checkout stage-03` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/03-durable-storage-boundary/stage.patch)
