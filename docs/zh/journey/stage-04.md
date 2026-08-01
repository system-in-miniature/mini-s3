# Stage 04 · 对象服务门面

### 目标

在一个带锁公开服务后连接 Bucket 与 DiskStorage，提供 Bucket 和对象操作。

??? note "交付文件"
    - `src/minis3/__init__.py`
    - `src/minis3/store.py`
    - `tests/test_storage.py`
    - `tests/test_versioning.py`

### 当前遇到的问题

领域层能计算下一份 Bucket，存储层也能发布它，但调用方仍需自己协调两者。缺少服务所有者时，一条路径可能只改内存不持久化，另一条路径可能在状态迁移中途与它竞争。

### 测试契约

#### 先看会坏在哪里

重启契约写入两个版本，再打开全新的 `MiniS3` 读取两份 Body，随后继续写入并要求新 ID。它同时暴露两类错误：状态没有真正发布到磁盘，或者恢复后的序列计数器复用了旧身份。

??? note "文件差异：tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    new file mode 100644
    index 0000000..c96a7a6
    --- /dev/null
    +++ b/tests/test_storage.py
    @@ -0,0 +1,32 @@
    +"""Disk tests pin the manifest publication crash boundary."""
    +
    +from pathlib import Path
    +import pytest
    +from minis3 import InjectedCrash, MiniS3, NoSuchKey, SequenceCounter
    +from minis3.bucket import Bucket
    +from minis3.storage import atomic, disk
    +from minis3.storage.disk import DiskStorage
    +
    +
    +class CrashOnce:
    +    def __init__(self, target: str) -> None:
    +        self.target = target
    +        self.used = False
    +
    +    def __call__(self, point: str) -> None:
    +        if point == self.target and not self.used:
    +            self.used = True
    +            raise InjectedCrash(point)
    +
    +
    +def test_restart_restores_versions_bodies_and_counter(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    first = store.put_object("b", "k", b"one")
    +
    +    reopened = MiniS3(tmp_path)
    +    second = reopened.put_object("b", "k", b"two")
    +
    +    assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
    +    assert second.version_id != first.version_id
    ```

**测试锁定什么**

这些契约通过公开服务检查持久化，包括重启、崩溃注入、Bucket 删除和序列恢复。

**如何构造反例**

它们捕获“内存成功但重开失败”的缺口，是编排层与存储层相遇的位置。

**关键测试语句**

```python
assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
```

**失败意味着什么**

在新实例上按旧版本 ID 读取，证明版本历史和字节都跨发布保存；只检查最新值证据更弱。

??? note "文件差异：tests/test_versioning.py"
    ```diff
    diff --git a/tests/test_versioning.py b/tests/test_versioning.py
    new file mode 100644
    index 0000000..389e45d
    --- /dev/null
    +++ b/tests/test_versioning.py
    @@ -0,0 +1,109 @@
    +"""Versioning is the central state-machine contract of M1."""
    +
    +from pathlib import Path
    +import pytest
    +from minis3 import BucketNotEmpty, MiniS3, NoSuchKey, NoSuchVersion, SequenceCounter, VersioningState
    +from minis3.bucket import Bucket
    +
    +
    +@pytest.mark.parametrize(
    +    ("initial", "requested", "allowed"),
    +    [
    +        (VersioningState.UNVERSIONED, VersioningState.UNVERSIONED, True),
    +        (VersioningState.UNVERSIONED, VersioningState.ENABLED, True),
    +        (VersioningState.UNVERSIONED, VersioningState.SUSPENDED, False),
    +        (VersioningState.ENABLED, VersioningState.UNVERSIONED, False),
    +        (VersioningState.ENABLED, VersioningState.ENABLED, True),
    +        (VersioningState.ENABLED, VersioningState.SUSPENDED, True),
    +        (VersioningState.SUSPENDED, VersioningState.UNVERSIONED, False),
    +        (VersioningState.SUSPENDED, VersioningState.ENABLED, True),
    +        (VersioningState.SUSPENDED, VersioningState.SUSPENDED, True),
    +    ],
    +)
    +def test_versioning_state_machine_exhaustive(
    +    initial: VersioningState,
    +    requested: VersioningState,
    +    allowed: bool,
    +) -> None:
    +    bucket = Bucket("b", versioning=initial)
    +
    +    if allowed:
    +        bucket.set_versioning(requested)
    +        assert bucket.versioning is requested
    +    else:
    +        with pytest.raises(ValueError):
    +            bucket.set_versioning(requested)
    +        assert bucket.versioning is initial
    +
    +
    +def test_unversioned_delete_defensively_preserves_named_history() -> None:
    +    bucket = Bucket("b")
    +    bucket.set_versioning(VersioningState.ENABLED)
    +    historical = bucket.put("k", b"named", SequenceCounter())
    +    bucket.versioning = VersioningState.UNVERSIONED
    +
    +    bucket.delete("k", SequenceCounter(10))
    +
    +    assert bucket.get("k", historical.version_id) == historical
    +
    +
    +def test_enabled_puts_stack_and_delete_marker_hides_history(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter())
    +    store.create_bucket("photos")
    +    null = store.put_object("photos", "cat.jpg", b"before")
    +    store.set_bucket_versioning("photos", VersioningState.ENABLED)
    +    first = store.put_object("photos", "cat.jpg", b"one")
    +    second = store.put_object("photos", "cat.jpg", b"two")
    +    marker = store.delete_object("photos", "cat.jpg")
    +
    +    assert [null.version_id, first.version_id, second.version_id] == [
    +        "null",
    +        "v00000002",
    +        "v00000003",
    +    ]
    +    assert marker is not None and marker.version_id == "v00000004"
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("photos", "cat.jpg")
    +    assert store.get_object(
    +        "photos", "cat.jpg", version_id=second.version_id
    +    ).body == b"two"
    +    assert store.head_object(
    +        "photos", "cat.jpg", version_id=first.version_id
    +    ).etag == first.etag
    +
    +
    +def test_specific_delete_removes_only_addressed_version(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter())
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    store.put_object("b", "k", b"old")
    +    new = store.put_object("b", "k", b"new")
    +
    +    removed = store.delete_object("b", "k", version_id=new.version_id)
    +
    +    assert removed == new
    +    assert store.get_object("b", "k").body == b"old"
    +    with pytest.raises(NoSuchVersion):
    +        store.get_object("b", "k", version_id=new.version_id)
    +
    +
    +def test_latest_marker_is_404_even_when_older_data_exists(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    old = store.put_object("b", "k", b"still here")
    +    marker = store.delete_object("b", "k")
    +
    +    with pytest.raises(NoSuchKey):
    +        store.head_object("b", "k")
    +    assert store.get_object("b", "k", version_id=old.version_id).body == b"still here"
    +    assert store.delete_object("b", "k", version_id=marker.version_id) == marker
    +    assert store.get_object("b", "k").body == b"still here"
    +
    +
    +def test_nonempty_bucket_cannot_be_deleted(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    store.put_object("b", "k", b"value")
    +    with pytest.raises(BucketNotEmpty):
    +        store.delete_bucket("b")
    ```

**测试锁定什么**

这里锁定完整公开版本状态机和 DELETE 含义。

**如何构造反例**

它区分未版本化删除、Marker 创建、指定版本删除、最新 Marker 导致 404，以及具名历史保留。

**关键测试语句**

```python
assert bucket.get("k", historical.version_id) == historical
```

**失败意味着什么**

这个防御性场景证明：即使恢复或外部构造中出现具名历史，未版本化删除也不能把它擦掉。

### 基本概念

应用服务负责协调已有所有者，而不是吞掉它们的职责。Bucket 仍决定合法历史，DiskStorage 仍决定发布和恢复，`MiniS3` 拥有公开操作、锁、查找以及两者之间的调用顺序。

实现先深拷贝候选 Bucket，对候选执行变更并持久化，最后才替换内存引用。因此发布失败时，原本可见的内存状态不会被污染。

### 为什么需要这个机制

只锁 Bucket 或只锁磁盘都不够，因为公开变更跨越两者。服务锁串行化“读取—检查—变更—发布”，候选发布则避免暴露未提交内存。

### 运行时心智模型

`put_object` 加锁、解析 Bucket、复制候选、把 PUT 委托给候选、持久化候选、替换 `_buckets`，最后返回 Version。GET/HEAD 在同一把锁下读取；HEAD 复用 GET，因为当前协议无关模型返回相同元数据值。

### 机制板块

#### 对象服务边界

在一个服务门面后协调加锁、Bucket 写时复制、持久化和公开对象操作。

??? note "文件差异：src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    new file mode 100644
    index 0000000..5d418b8
    --- /dev/null
    +++ b/src/minis3/store.py
    @@ -0,0 +1,104 @@
    +"""Public service facade joining buckets, object state, and list projections."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable
    +from copy import deepcopy
    +from pathlib import Path
    +from threading import RLock
    +
    +from .bucket import Bucket, SequenceCounter, VersioningState
    +from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    +from .model import ObjectVersion, Version
    +from .storage import DiskStorage
    +
    +
    +class MiniS3:
    +    """A deterministic collection of strongly consistent buckets."""
    +
    +    def __init__(
    +        self,
    +        root: str | Path,
    +        *,
    +        counter: Callable[[], int] | None = None,
    +        crash_injector: Callable[[str], None] | None = None,
    +    ) -> None:
    +        self.root = Path(root)
    +        self._counter = counter or SequenceCounter()
    +        self._storage = DiskStorage(root, crash_injector=crash_injector)
    +        self._buckets, maximum_sequence = self._storage.load_buckets()
    +        ensure = getattr(self._counter, "ensure_at_least", None)
    +        if ensure is not None:
    +            ensure(maximum_sequence + 1)
    +        self._lock = RLock()
    +
    +
    +    def create_bucket(self, name: str) -> None:
    +        with self._lock:
    +            if name in self._buckets:
    +                raise BucketAlreadyExists(name)
    +            bucket = Bucket(name)
    +            self._storage.create_bucket(bucket)
    +            self._buckets[name] = bucket
    +
    +
    +    def delete_bucket(self, name: str) -> None:
    +        with self._lock:
    +            bucket = self._bucket(name)
    +            if bucket.records:
    +                raise BucketNotEmpty(name)
    +            self._storage.delete_bucket(name)
    +            del self._buckets[name]
    +
    +
    +    def set_bucket_versioning(
    +        self, name: str, state: VersioningState | str
    +    ) -> None:
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(name))
    +            candidate.set_versioning(state)
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[name] = candidate
    +
    +
    +    def put_object(self, bucket: str, key: str, body: bytes) -> Version:
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(bucket))
    +            result = candidate.put(key, body, self._counter)
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[bucket] = candidate
    +            return result
    +
    +
    +    def get_object(
    +        self, bucket: str, key: str, *, version_id: str | None = None
    +    ) -> Version:
    +        with self._lock:
    +            return self._bucket(bucket).get(key, version_id)
    +
    +
    +    def head_object(
    +        self, bucket: str, key: str, *, version_id: str | None = None
    +    ) -> Version:
    +        """Return object metadata; M1 reuses the immutable Version value."""
    +
    +        return self.get_object(bucket, key, version_id=version_id)
    +
    +
    +    def delete_object(
    +        self, bucket: str, key: str, *, version_id: str | None = None
    +    ) -> ObjectVersion | None:
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(bucket))
    +            result = candidate.delete(key, self._counter, version_id)
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[bucket] = candidate
    +            return result
    +
    +
    +    def _bucket(self, name: str) -> Bucket:
    +        try:
    +            return self._buckets[name]
    +        except KeyError as exc:
    +            raise NoSuchBucket(name) from exc
    +
    ```

**是什么，为什么现在需要**

这是公开应用边界，协调锁、聚合迁移、持久化与恢复。

**在运行时做什么**

所有公开 Bucket/对象调用从这里进入。成功变更依次跨过 Bucket 和 DiskStorage；读取解析当前内存聚合。

**关键代码**

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
```

**关键语句理解**

候选先发布，之后才成为进程可见 Bucket。反过来会让失败的磁盘写入泄漏成“当前可见但重启消失”的状态。

#### 公开导出接线

让新服务可导入，但不为常规包接线单独展开概念讲解。

??? note "支撑文件差异（1 个文件）"
    **`src/minis3/__init__.py`**

    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 8a3d1c7..11378e1 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -1,3 +1,6 @@
     """Public API for the MiniS3 teaching implementation."""
     from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
    +from .bucket import SequenceCounter, VersioningState
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
    +from .store import MiniS3
    +from .storage import InjectedCrash
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/04-object-service/tests.txt)`。15 个用例覆盖服务编排与版本行为，但还不证明 Listing 投影或 Manifest rename 两侧的注入崩溃结果。

### 需要真正记住的内容

服务拥有编排和锁，Bucket 拥有领域迁移，存储拥有持久化；先 persist 再 swap 让内存与已提交状态一致。

### 用自己的话讲清楚

`MiniS3` 把领域组件和存储组件组成一次一致的公开操作。它串行化完整迁移，在暴露候选 Bucket 前先发布，所以写入失败时当前内存与重启可见状态会留在同一侧。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/02-objects-etag.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-03...stage-04)

完成后可运行 `git checkout stage-04` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/04-object-service/stage.patch)
