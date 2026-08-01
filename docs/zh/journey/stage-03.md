# Stage 03 · 持久化存储边界

### 目标

用不可变 Artifact 与最后发布的 Manifest 为 Bucket 状态建立持久表示。

### 交付文件

- `src/minis3/storage/__init__.py`
- `src/minis3/storage/atomic.py`
- `src/minis3/storage/disk.py`
- `tests/test_storage_boundary.py`

### 当前遇到的问题

Stage 02 已有正确内存历史，但进程退出就会全部消失。直接覆盖一个可变 JSON 也不够：崩溃可能留下半份文件，或者留下尚未持久化的目录项。

### 先看会坏在哪里

存储契约写入 Bucket 后，用同一目录创建全新的 `DiskStorage`，要求恢复完全相同的 Body、ETag、版本和最大序列。缺少 fsync 或发布顺序错误可能在进程内读取时看不出来，却会在这次重启观察中失败。

### 基本概念

原子可见性与持久性不是一件事。`os.replace` 让读者看到旧完整文件或新完整文件；文件 `fsync` 持久化内容字节，父目录 `fsync` 持久化名称变化。

MiniS3 保存不可变数据/元数据 Artifact 与较小的可变 `manifest.json`。Manifest 是权威：重启后只有被成功发布 Manifest 引用的 Artifact 才可见。

### 为什么需要这个机制

直接更新一个大型可变状态文件会让每次对象写入都重写共享状态并扩大崩溃面。不可变 Artifact 可以先安全落盘，最后发布引用则给恢复过程一个明确提交记录，并允许清除孤儿数据。

### 运行时心智模型

`DiskStorage.persist_bucket` 先写缺失的不可变 Artifact，再为 Manifest 调用 `atomic_write`。后者写临时文件、flush、文件 fsync、替换最终名称、父目录 fsync。启动时只加载 Manifest 引用并清理其余内容。

### 逐文件走读

#### `src/minis3/storage/atomic.py`

##### 是什么，为什么现在需要

这个文件拥有可复用的文件系统发布原语，不负责 S3 领域决策。

##### 在运行时做什么

当文件或目录项必须跨崩溃保存时，DiskStorage 调用它；这里是检查可见性与持久化顺序的最底层边界。

##### 关键代码

```python
os.replace(temporary, path)
fsync_directory(path.parent)
```

##### 关键语句理解

replace 改变最终名称指向哪份完整文件，随后的目录 fsync 才持久化这次 rename。省略第二行可能出现“现在看得到，掉电后却消失”。

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

##### 是什么，为什么现在需要

这是 Bucket 磁盘布局、Manifest 发布和启动恢复的唯一所有者。

##### 在运行时做什么

它把 Bucket 历史变成不可变 `.data`/`.json` Artifact 和 Manifest 引用，并在启动时重建 Bucket。

##### 关键代码

```python
self._inject("before_manifest_publish")
atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
self._inject("after_manifest_publish")
```

##### 关键语句理解

Manifest 写入被两个命名崩溃点夹住，因为它正是可见性边界。此前的 Artifact 尚未被引用；此后恢复必须把新状态视为已提交。

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

#### `src/minis3/storage/__init__.py`

##### 是什么，为什么现在需要

这个包边界导出持久适配器，以及后续崩溃实验使用的故意崩溃类型。

##### 在运行时做什么

它提供稳定导入，同时保持布局辅助函数为内部细节。

##### 关键语句理解

导出 `DiskStorage` 明确存储所有者；导出 `InjectedCrash` 让崩溃边界可测试，而不必公开全部 helper。

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

#### `tests/test_storage_boundary.py`

##### 是什么，为什么现在需要

这是第一条存储契约，证明一个完整 Bucket 能跨越类似进程重启的边界。

##### 在运行时做什么

它持久化状态、创建新适配器，再比较恢复后的值与序列元数据。它比序列化单测更广，但还没到公开 MiniS3 服务。

##### 关键代码

```python
recovered, maximum_sequence = DiskStorage(tmp_path).load_buckets()
```

##### 关键语句理解

必须使用新适配器；读取原内存 Bucket 无法证明字节已发布并可恢复。返回 `maximum` 还能避免未来复用序列。

??? note "文件差异：tests/test_storage_boundary.py"
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

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`。它证明正常发布/重启路径；Stage 07、08 会分别证明崩溃点和目录 fsync 清理。

### 需要真正记住的内容

rename 提供原子可见性，fsync 提供持久性，Manifest 是提交记录；Artifact 存在不代表它已经可见。

### 用自己的话讲清楚

MiniS3 先写不可变对象 Artifact，最后原子发布 Manifest。恢复只信任 Manifest，所以崩溃可以留下多余文件，却不能暴露半发布对象。rename 是可见性点，父目录 fsync 让这个决定跨重启保存。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-02...stage-03)

完成后可运行 `git checkout stage-03` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/03-durable-storage-boundary/stage.patch)
