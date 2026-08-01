# Stage 05 · 版本历史投影

### 目标

投影完整历史，同时保持 null 版本、具名版本和删除标记可区分。

??? note "交付文件"
    - `src/minis3/__init__.py`
    - `src/minis3/listing.py`
    - `src/minis3/store.py`
    - `tests/test_versioning.py`

### 当前遇到的问题

GET 只返回一份被寻址的数据版本，无法解释最新值或 Marker 背后隐藏的历史。管理和恢复视图需要看到全部保留项，并有足够字段区分它们的含义。

### 先看会坏在哪里

暂停删除契约先创建具名历史，再写 `null` 值，最后不带版本 ID 删除。预期历史包含新的 `null` Marker 和旧具名版本，但不再包含被替换的 `null` 数据。简单“列出全部值”会报告错误状态。

### 基本概念

投影是从已有状态派生的只读形状。`ListedVersion` 不成为第二个历史所有者；它只是把 `Version` 或 `DeleteMarker` 转成调用方需要的字段。`is_latest` 由单个 Key 的新到旧位置决定，不是全局比较 ID 字符串。

### 为什么需要这个机制

返回内部原始对象会把调用方耦合到存储字段并诱发修改；只返回当前数据又会抹掉 Marker 和非当前版本。显式投影既保留语义，也让聚合继续保持权威。

### 运行时心智模型

服务加锁，把 Bucket records 交给 `list_object_versions`。纯函数按精确 Key 前缀过滤、确定性遍历 Key、展开新到旧历史、只把索引 0 标成 latest，再返回不可变结果。

### 机制板块

#### 版本历史投影

把 Bucket 的新到旧历史投影成稳定公开值，同时保留 null 版本和删除标记。

??? note "查看本板块差异（3 个文件）"
    **`src/minis3/listing.py`**

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

    **`src/minis3/store.py`**

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

    **`tests/test_versioning.py`**

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


**讲解: `src/minis3/listing.py`**

**是什么，为什么现在需要**

这个读取侧模块引入响应值与纯历史投影。

**在运行时做什么**

它不修改 records，只输出稳定序列，携带 Key、ID、数据存在时的 ETag/size、Marker 标记与 latest 标记。

**关键代码**

```python
etag=item.etag if is_data else None,
```

**关键语句理解**

Marker 没有基于 Body 的 ETag。显式使用 `None` 保留区别，而不是伪造一个空对象指纹。

**讲解: `src/minis3/store.py`**

**是什么，为什么现在需要**

公开服务增加带锁的历史读取方法。

**在运行时做什么**

它解析 Bucket 并委托纯 Listing 函数，同时阻止并发变更在读取中途改变快照。

**关键代码**

```python
return list_object_versions(self._bucket(bucket).records, prefix=prefix)
```

**关键语句理解**

服务传入 records，但不重复投影逻辑。这样职责清晰，纯函数也能独立理解。

**讲解: `tests/test_versioning.py`**

**是什么，为什么现在需要**

三个新场景锁定未版本化替换、暂停替换和暂停删除后的投影。

**在运行时做什么**

它们观察真实服务变更后的公开历史，因此证据同时覆盖 Bucket 与投影，而不是只测虚构输入。

**关键代码**

```python
assert marker is not None and marker.version_id == "null"
```

**关键语句理解**

暂停不表示删除变成物理删除。新 Marker 占据公开 `null` 槽，具名历史仍可寻址。

#### 公开导出接线

导出投影结果类型；其行为由上面的投影板块负责。

??? note "查看本板块差异（1 个文件）"
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


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`。累计测试证明跨版本状态的投影语义；当前对象分页属于 Stage 06。

### 需要真正记住的内容

读取投影解释状态但不拥有状态。null 数据、具名数据、Marker 保持可区分，“latest” 只属于单个精确 Key 历史。

### 用自己的话讲清楚

版本 Listing 是 Bucket 历史的纯视图。它保留 GET 故意隐藏的条目，把每个 Key 的历史头标为 latest，并让 Marker 的数据字段保持为空，使调用方能还原发生了什么而不修改源状态。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-04...stage-05)

完成后可运行 `git checkout stage-05` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/05-version-history/stage.patch)
