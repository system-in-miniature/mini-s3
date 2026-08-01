# Stage 06 · Listing 与目录幻觉

### 目标

从扁平 Key 推导当前 contents 与 common prefixes，并提供绑定查询的 opaque 分页 token。

??? note "交付文件"
    - `src/minis3/__init__.py`
    - `src/minis3/listing.py`
    - `src/minis3/store.py`
    - `tests/test_listing.py`

### 当前遇到的问题

版本 Listing 已能展示历史，但普通对象 Listing 仍不知道怎样处理 prefix、delimiter 和分页。把含斜杠 Key 当成真实目录会违背 Stage 01，并制造 S3 根本不存储的状态。

### 先看会坏在哪里

Delimiter 契约存入 `a.txt`、`raw` 和多个 `photos/...` Key。根目录用 `/` Listing 时必须返回两个 contents 和唯一的 `photos/` common prefix。如果实现遍历目录或返回所有 photo Key，公开投影就错了。

### 测试契约

??? note "文件差异：tests/test_listing.py"
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

**测试锁定什么**

五条契约覆盖目录幻觉、组合分页、Marker 隐藏、版本展开和无效 token。

**如何构造反例**

它们通过 `MiniS3` 建立状态并观察公开结果，把模型语义连接到最终读取视图。

**关键测试语句**

```python
assert root.common_prefixes == ("photos/",)
```

**失败意味着什么**

多个扁平 Key 在根视图中折叠成一个投影前缀；这个 tuple 不表示存储了 `photos/` 对象或目录。

### 基本概念

`prefix` 按字符串开头过滤。`delimiter` 在剩余后缀第一次出现的位置分组出 `common_prefix`；它是计算视图，不是存储的文件夹。对象和 common prefix 都占结果槽位，所以分页必须共同计数。

Continuation token 是不透明游标。MiniS3 把 offset 与 prefix、delimiter 一起编码，避免把一个查询的 token 用到另一个查询后悄悄跳过不同结果。

### 为什么需要这个机制

暴露裸 offset 会泄漏实现并允许查询错配；把 common prefix 当对象则会混淆 HEAD/GET 与删除。单一纯投影既保持扁平存储，又提供熟悉的目录式浏览。

### 运行时心智模型

服务锁住 Bucket 快照并调用 `list_objects`。函数选择每个 Key 的当前可见数据，应用 prefix/delimiter 投影，对组合结果排序，解码绑定查询的 offset，截取一页，并在仍有结果时生成下一 token。

### 机制板块

#### 目录式 Listing 投影

从扁平精确 Key 派生 prefix、delimiter、分页与 continuation 行为，而不创建真实目录。

??? note "文件差异：src/minis3/listing.py"
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

**是什么，为什么现在需要**

读取侧现在除版本历史外，还拥有当前对象 Listing、delimiter 分组与分页 token。

**在运行时做什么**

它不修改 Bucket records，返回不可变 `contents`、`common_prefixes` 与 `next_token`。

**关键代码**

```python
return urlsafe_b64encode(payload).decode().rstrip("=")
```

**关键语句理解**

编码隐藏游标表示；payload 还带查询形状，因此解码时能拒绝属于其他 prefix 或 delimiter 的游标。

??? note "文件差异：src/minis3/store.py"
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

**是什么，为什么现在需要**

服务增加当前 Listing 的公开带锁入口。

**在运行时做什么**

它提供一致 records 快照，并把全部只读投影规则委托给 `listing.py`。

**关键代码**

```python
with self._lock:
```

**关键语句理解**

纯投影也需要稳定输入。锁防止并发 PUT/DELETE 在分页构造中途改变 Key 集合。

#### 公开导出接线

导出 Listing 值，同时让投影语义继续集中在核心板块。

??? note "支撑文件差异（1 个文件）"
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


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-directory-illusion/tests.txt)`。五个新用例证明投影与 token 行为，所有早期历史测试继续累计执行。

### 需要真正记住的内容

Key 始终扁平；目录只是读取幻觉；contents 与 prefixes 共享页容量；continuation token 属于一个精确查询。

### 用自己的话讲清楚

MiniS3 通过在 delimiter 处对扁平字符串分组来展示类似目录的 Listing，从未创建文件夹。分页针对组合投影结果，opaque token 又绑定 prefix 与 delimiter，因此不能换一套查询语义继续使用。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/04-listing.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-05...stage-06)

完成后可运行 `git checkout stage-06` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/06-directory-illusion/stage.patch)
