# Stage 05 · 版本历史投影

### 目标

公开完整历史，使 null 版本、具名版本与删除标记保持可区分。

### 动手任务

从stage-04开始，实现 `list_object_versions(records, prefix=...)` 与 `MiniS3.list_object_versions`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_versioning.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        当前可见性与保留历史，是同一记录的两种投影。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`

### 对应真实 S3 的一课

当前可见性与保留历史，是同一记录的两种投影。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-04...stage-05)

完成后可运行 `git checkout stage-05` 对照你的结果。

??? note "先做后看：stage.patch"
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
