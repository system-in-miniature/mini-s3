# Stage 10 · Multipart 持久暂存

### 目标

持久化私有 Multipart 上传并原子替换 Part，同时不发布对象。

### 交付文件

??? note "展开交付文件"
    - `src/minis3/__init__.py`
    - `src/minis3/bucket.py`
    - `src/minis3/model.py`
    - `src/minis3/storage/disk.py`
    - `src/minis3/store.py`
    - `tests/test_multipart.py`

### 当前遇到的问题

Stage 09 只能验证抽象暂存 Part；真实客户端需要 upload ID 和 Part 字节跨重试、重启保存。这些字节在完成发布一个完整对象以前，必须对普通 GET/List 不可见。

### 先看会坏在哪里

第一条集成契约为 Key `right` 创建上传，再尝试用 Key `wrong` 和 Part 编号 `0`、`10001` 上传。每次都必须在写暂存前失败，否则 upload ID 会跨 Key 混用或产生非法 Part 文件。

### 基本概念

Staging 是持久私有状态，不是部分可见对象。每次上传由 `(bucket, key, upload_id)` 标识，并拥有自己的 `parts/` 目录；重复上传相同 Part 编号会原子替换这个暂存槽。

对象模型增加创建时间和可选 `multipart_upload_id` 来源，供未来完成后的版本记录。这些字段不会让 Staging 可见；只有 Bucket Manifest 引用的 `ObjectRecord` 才能做到。

### 为什么需要这个机制

只在内存保存 Part 会让重试和重启不可靠；直接写入对象历史又会暴露不完整值。独立持久命名空间既保存工作，又维持前面建立的单一发布边界。

### 运行时心智模型

服务分配确定性 upload ID，让 DiskStorage 创建 `uploads/<id>/upload.json` 和 `parts/`。`upload_part` 校验编号与上传身份，再原子写一个编号 `.data` 文件。Abort 只删除这次私有上传目录。

### 逐文件走读

#### `src/minis3/model.py`

##### 是什么，为什么现在需要

Version 和 Marker 增加时间戳；数据版本还可记录完成它的 Multipart upload。

##### 在运行时做什么

后续生命周期和恢复会使用这些字段；它们仍是已发布历史上的不可变元数据。

##### 关键代码

```python
multipart_upload_id: str | None = None
```

##### 关键语句理解

`None` 表示普通 PUT；Multipart 完成版本可保留来源，但不会让上传过程本身变成可见历史。

??? note "文件差异：src/minis3/model.py"
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

##### 是什么，为什么现在需要

Bucket PUT 接受可选的外部 ETag、时间戳与 Multipart 来源，同时保留普通 PUT 默认值。

##### 在运行时做什么

完成操作会复用同一版本迁移，而不是发明第二条发布路径。

##### 关键代码

```python
etag=content_etag(body) if etag is None else etag,
```

##### 关键语句理解

普通 PUT 仍计算 whole-body ETag；Multipart 完成可以传入验证后的组合 ETag。按组装 Body 重算会得到错误语义。

??? note "文件差异：src/minis3/bucket.py"
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

##### 是什么，为什么现在需要

DiskStorage 增加私有上传布局、原子 Part 写入、身份校验、删除和重启恢复。

##### 在运行时做什么

它像管理对象 Artifact 一样管理持久 Staging，但普通 Manifest/List 从不读取 `uploads/`。

##### 关键代码

```python
atomic_write(directory / "parts" / f"{part.part_number:05d}.data", part.body)
```

##### 关键语句理解

Part 编号选择稳定文件名，`atomic_write` 完整替换它；重试不会留下半旧半新的字节。

??? note "文件差异：src/minis3/storage/disk.py"
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

##### 是什么，为什么现在需要

公开服务增加 initiate、upload-part、abort 编排，以及可注入 clock 和最小 Part 大小。

##### 在运行时做什么

它在同一把锁下校验公开参数、分配确定性上传身份，再把私有字节委托给 DiskStorage。

##### 关键代码

```python
upload_id=f"u{sequence:08d}",
```

##### 关键语句理解

Upload ID 延续单调序列纪律，使重启恢复和学习追踪可复现，而不是依赖随机 UUID。

??? note "文件差异：src/minis3/store.py"
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

##### 是什么，为什么现在需要

Multipart 值与失败加入受支持包级 API。

##### 在运行时做什么

调用方可以持有 receipt 并捕获 `NoSuchUpload`，无需导入存储内部实现。

##### 关键语句理解

公开的是领域契约，不是私有磁盘布局。

??? note "文件差异：src/minis3/__init__.py"
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

##### 是什么，为什么现在需要

第一条持久 Multipart 测试锁定上传身份和合法 Part 编号范围。

##### 在运行时做什么

它通过 `MiniS3` 进入，因此失败同时覆盖服务校验与存储身份查找。

##### 关键代码

```python
store.upload_part("b", "wrong", upload.upload_id, 1, b"x")
```

##### 关键语句理解

Upload ID 不能全局互换：寻址的 Bucket 与 Key 必须和持久元数据匹配，之后才能写 Part。

??? note "文件差异：tests/test_multipart.py"
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

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/10-multipart-staging/tests.txt)`。它证明身份与范围拒绝，累计测试守住早期对象行为；完成可见性刻意留到下一阶段。

### 需要真正记住的内容

Staging 持久但私有；上传身份包含 Bucket 和 Key；同编号重试原子替换；只有 Bucket Manifest 发布才能创建对象。

### 用自己的话讲清楚

MiniS3 把未完成 Multipart 工作保存在独立持久命名空间。服务校验上传身份和 Part 编号，DiskStorage 原子替换编号 Part 文件；由于尚未发布 ObjectRecord，普通 GET/List 完全不受影响。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-09...stage-10)

完成后可运行 `git checkout stage-10` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/10-multipart-staging/stage.patch)
