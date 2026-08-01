# Stage 05 · 版本历史投影

### 目标

公开完整历史，使 null 版本、具名版本与删除标记保持可区分。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_versioning.py`

### 机制走读

#### 所有权与数据流

变更仍由 `Bucket` 负责；`listing.py` 把有序历史展平成只读 `ListedVersion` 行，同时保留 latest 与 delete-marker 标记。

#### 失败与排查

先检查存储的 Tuple，再判断投影；null 槽替换错误属于变更问题，历史正确但顺序或标记错误才属于 Listing 问题。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/listing.py`

读取侧投影与分页逻辑。

由服务读取路径调用；把存储历史转换成排序、分页的响应值，不修改状态。

**变化锚点:** `ListedVersion`, `ListObjectVersionsResult`, `list_object_versions`

??? note "文件差异：src/minis3/listing.py"
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

#### `src/minis3/store.py`

协调领域逻辑与持久化的应用服务。

接收公开调用，拥有加锁与编排，再委托给领域、投影和存储边界。

**变化锚点:** `list_object_versions`, `_bucket`

??? note "文件差异：src/minis3/store.py"
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

#### `src/minis3/__init__.py`

受支持的包级公开接口。

由用户导入触达；接线错误会在运行时流程开始前表现为名称缺失。

**变化锚点:** 配置、导出或文档变化

??? note "文件差异：src/minis3/__init__.py"
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

#### `tests/test_versioning.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `test_unversioned_put_replaces_null_and_delete_removes_it`, `test_enabled_puts_stack_and_delete_marker_hides_history`, `test_suspended_put_replaces_null_but_preserves_named_history`, `test_latest_marker_is_404_even_when_older_data_exists`, `test_suspended_delete_replaces_null_with_null_marker`, `test_nonempty_bucket_cannot_be_deleted`

??? note "文件差异：tests/test_versioning.py"
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

### 验证证据

`uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`

本阶段新增 3 个可执行用例，入口为 `test_unversioned_put_replaces_null_and_delete_removes_it`、`test_suspended_put_replaces_null_but_preserves_named_history`、`test_suspended_delete_replaces_null_with_null_marker`。它们在机制走读之后运行，并与此前 Stage 的用例一起守住累计行为。

### 概念检查

本阶段完成后，哪条不变量必须保持成立？

??? note "答案"
    当前可见性与保留历史，是同一记录的两种投影。

### 代码阅读检查

从 `src/minis3/listing.py` 的 `ListedVersion` 开始：进入这个边界的状态或值是什么，结果又交给哪个所有者？

??? note "答案"
    由服务读取路径调用；把存储历史转换成排序、分页的响应值，不修改状态。

### 面试表达

当前可见性与保留历史，是同一记录的两种投影。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-04...stage-05)

完成后可运行 `git checkout stage-05` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/05-version-history/stage.patch)
