# Stage 14 · 确定性生命周期过期

### 目标

把纯过期决策与由注入时钟驱动的显式变更 tick 分开。

??? note "交付文件"
    - `src/minis3/__init__.py`
    - `src/minis3/lifecycle.py`
    - `src/minis3/store.py`
    - `tests/test_lifecycle.py`

### 当前遇到的问题

Version 已有创建时间，但没有任何机制让它们过期。把时间读取藏进策略或后台线程，会让边界行为不确定，并把“应该发生什么”和“现在执行”混在一起。

### 先看会坏在哪里

纯边界契约在时间 `9.999` 与 `10.0` 对同一历史求值。阈值前不能有 action，到达时必须出现。隐藏 wall clock 或使用严格 `>` 会让边界 flaky 或晚一个 tick。

### 基本概念

策略求值是不可变历史、规则和显式 `now` 的纯计算，输出 `LifecycleAction` 决策。`lifecycle_tick` 是独立变更边界，在服务锁内应用决策，并只在状态变化时持久化。

当前数据版本过期会创建删除标记，使旧历史继续隐藏；非当前版本过期则物理移除被寻址的历史项。

### 为什么需要这个机制

纯求值可无副作用重复推理；注入 clock 让测试和重放确定；显式 tick 还明确了锁与持久化义务从哪里开始。

### 运行时心智模型

调用方用规则调用 `lifecycle_tick`。服务取得注入时间、深拷贝 Bucket、调用 `evaluate_expiration`、通过 Bucket 删除语义应用每个 action；有 action 时持久化并替换候选，最后返回 action 列表。

### 逐文件走读

#### `src/minis3/lifecycle.py`

??? note "文件差异：src/minis3/lifecycle.py"
    ```diff
    diff --git a/src/minis3/lifecycle.py b/src/minis3/lifecycle.py
    new file mode 100644
    index 0000000..ca0c3f0
    --- /dev/null
    +++ b/src/minis3/lifecycle.py
    @@ -0,0 +1,103 @@
    +"""Pure lifecycle expiration decisions for an explicit manual tick.
    +
    +Evaluation reads an immutable-style snapshot and returns actions; it never
    +mutates records or reads a clock. The service injects ``now`` and applies the
    +actions only when the caller explicitly requests a tick.
    +"""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from enum import StrEnum
    +
    +from .model import ObjectRecord, Version
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ExpirationRule:
    +    """Age thresholds for matching current and noncurrent data versions."""
    +
    +    rule_id: str
    +    prefix: str = ""
    +    expire_current_after: float | None = None
    +    expire_noncurrent_after: float | None = None
    +
    +    def __post_init__(self) -> None:
    +        thresholds = (self.expire_current_after, self.expire_noncurrent_after)
    +        if all(value is None for value in thresholds):
    +            raise ValueError("an expiration rule needs at least one threshold")
    +        if any(value is not None and value < 0 for value in thresholds):
    +            raise ValueError("expiration ages must be non-negative")
    +
    +
    +class LifecycleActionKind(StrEnum):
    +    """The two deliberately small M2 lifecycle transitions."""
    +
    +    EXPIRE_CURRENT = "expire_current"
    +    EXPIRE_NONCURRENT = "expire_noncurrent"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LifecycleAction:
    +    """One deterministic mutation selected by a named rule."""
    +
    +    rule_id: str
    +    key: str
    +    version_id: str
    +    kind: LifecycleActionKind
    +
    +
    +def _old_enough(created_at: float, threshold: float | None, now: float) -> bool:
    +    return threshold is not None and now - created_at >= threshold
    +
    +
    +def evaluate_expiration(
    +    records: dict[str, ObjectRecord],
    +    rules: list[ExpirationRule] | tuple[ExpirationRule, ...],
    +    *,
    +    now: float,
    +) -> tuple[LifecycleAction, ...]:
    +    """Return de-duplicated actions without changing the supplied records."""
    +
    +    actions: list[LifecycleAction] = []
    +    selected: set[tuple[str, str, LifecycleActionKind]] = set()
    +    for key in sorted(records):
    +        record = records[key]
    +        if not record.versions:
    +            continue
    +        for rule in rules:
    +            if not key.startswith(rule.prefix):
    +                continue
    +            current = record.versions[0]
    +            identity = (key, current.version_id, LifecycleActionKind.EXPIRE_CURRENT)
    +            if (
    +                isinstance(current, Version)
    +                and identity not in selected
    +                and _old_enough(
    +                    current.created_at, rule.expire_current_after, now
    +                )
    +            ):
    +                selected.add(identity)
    +                actions.append(
    +                    LifecycleAction(rule.rule_id, key, current.version_id, identity[2])
    +                )
    +            for version in record.versions[1:]:
    +                identity = (
    +                    key,
    +                    version.version_id,
    +                    LifecycleActionKind.EXPIRE_NONCURRENT,
    +                )
    +                if (
    +                    isinstance(version, Version)
    +                    and identity not in selected
    +                    and _old_enough(
    +                        version.created_at, rule.expire_noncurrent_after, now
    +                    )
    +                ):
    +                    selected.add(identity)
    +                    actions.append(
    +                        LifecycleAction(
    +                            rule.rule_id, key, version.version_id, identity[2]
    +                        )
    +                    )
    +    return tuple(actions)
    ```

##### 是什么，为什么现在需要

这个纯策略模块定义过期规则、action 值和决策求值。

##### 在运行时做什么

它读取历史并返回应该改变什么，从不调用存储或修改 Bucket records。

##### 关键代码

```python
return threshold is not None and now - created_at >= threshold
```

##### 关键语句理解

`>=` 让策略边界包含阈值且确定；`None` 表示该类别没有过期规则，不是年龄零。

#### `src/minis3/store.py`

??? note "文件差异：src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index e47e1ac..c2bdc5b 100644
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

    @@ -8,10 +13,27 @@ from pathlib import Path
     from threading import RLock
     from time import time

    -from .conditional import require_if_match, require_if_none_match
     from .bucket import Bucket, SequenceCounter, VersioningState
    -from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket, NoSuchKey, NoSuchVersion
    -from .listing import ListObjectsResult, ListObjectVersionsResult, list_object_versions, list_objects
    +from .conditional import require_if_match, require_if_none_match
    +from .errors import (
    +    BucketAlreadyExists,
    +    BucketNotEmpty,
    +    NoSuchBucket,
    +    NoSuchKey,
    +    NoSuchVersion,
    +)
    +from .lifecycle import (
    +    ExpirationRule,
    +    LifecycleAction,
    +    LifecycleActionKind,
    +    evaluate_expiration,
    +)
    +from .listing import (
    +    ListObjectsResult,
    +    ListObjectVersionsResult,
    +    list_object_versions,
    +    list_objects,
    +)
     from .model import ObjectVersion, Version
     from .multipart import (
         MAX_PART_NUMBER,
    @@ -50,7 +72,6 @@ class MiniS3:
                 ensure(maximum_sequence + 1)
             self._lock = RLock()

    -
         def create_bucket(self, name: str) -> None:
             with self._lock:
                 if name in self._buckets:
    @@ -59,7 +80,6 @@ class MiniS3:
                 self._storage.create_bucket(bucket)
                 self._buckets[name] = bucket

    -
         def delete_bucket(self, name: str) -> None:
             with self._lock:
                 bucket = self._bucket(name)
    @@ -68,7 +88,6 @@ class MiniS3:
                 self._storage.delete_bucket(name)
                 del self._buckets[name]

    -
         def set_bucket_versioning(
             self, name: str, state: VersioningState | str
         ) -> None:
    @@ -78,7 +97,6 @@ class MiniS3:
                 self._storage.persist_bucket(candidate)
                 self._buckets[name] = candidate

    -
         def put_object(
             self,
             bucket: str,
    @@ -97,7 +115,6 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    -
         def get_object(
             self,
             bucket: str,
    @@ -113,7 +130,6 @@ class MiniS3:
                 require_if_none_match(result.etag, if_none_match)
                 return result

    -
         def head_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> Version:
    @@ -121,7 +137,6 @@ class MiniS3:

             return self.get_object(bucket, key, version_id=version_id)

    -
         def delete_object(
             self,
             bucket: str,
    @@ -142,7 +157,6 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    -
         def list_objects(
             self,
             bucket: str,
    @@ -161,14 +175,12 @@ class MiniS3:
                     continuation_token=continuation_token,
                 )

    -
         def list_object_versions(
             self, bucket: str, *, prefix: str = ""
         ) -> ListObjectVersionsResult:
             with self._lock:
                 return list_object_versions(self._bucket(bucket).records, prefix=prefix)

    -
         def create_multipart_upload(
             self, bucket: str, key: str
         ) -> MultipartUpload:
    @@ -187,7 +199,6 @@ class MiniS3:
                 self._storage.create_multipart_upload(upload)
                 return upload

    -
         def upload_part(
             self,
             bucket: str,
    @@ -206,7 +217,6 @@ class MiniS3:
                 self._storage.write_multipart_part(bucket, key, upload_id, part)
                 return part.receipt

    -
         def complete_multipart_upload(
             self,
             bucket: str,
    @@ -239,7 +249,6 @@ class MiniS3:
                 self._storage.remove_multipart_upload(bucket, key, upload_id)
                 return result

    -
         def abort_multipart_upload(
             self, bucket: str, key: str, upload_id: str
         ) -> None:
    @@ -249,6 +258,37 @@ class MiniS3:
                 self._bucket(bucket)
                 self._storage.remove_multipart_upload(bucket, key, upload_id)

    +    def lifecycle_tick(
    +        self,
    +        bucket: str,
    +        rules: list[ExpirationRule] | tuple[ExpirationRule, ...],
    +    ) -> tuple[LifecycleAction, ...]:
    +        """Evaluate at the injected time and atomically apply selected actions."""
    +
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(bucket))
    +            now = self._clock()
    +            actions = evaluate_expiration(
    +                candidate.records, rules, now=now
    +            )
    +            for action in actions:
    +                if action.kind is LifecycleActionKind.EXPIRE_CURRENT:
    +                    current = candidate.records[action.key].versions[0]
    +                    if current.version_id == action.version_id:
    +                        candidate.delete(
    +                            action.key, self._counter, now=now
    +                        )
    +                else:
    +                    candidate.delete(
    +                        action.key,
    +                        self._counter,
    +                        action.version_id,
    +                        now=now,
    +                    )
    +            if actions:
    +                self._storage.persist_bucket(candidate)
    +                self._buckets[bucket] = candidate
    +            return actions

         @staticmethod
         def _current_etag(bucket: Bucket, key: str) -> str | None:
    @@ -257,7 +297,6 @@ class MiniS3:
             except NoSuchKey:
                 return None

    -
         @staticmethod
         def _addressed_etag(
             bucket: Bucket, key: str, version_id: str | None
    @@ -267,10 +306,8 @@ class MiniS3:
             except (NoSuchKey, NoSuchVersion):
                 return None

    -
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
             except KeyError as exc:
                 raise NoSuchBucket(name) from exc
    -
    ```

##### 是什么，为什么现在需要

服务增加把纯 action 转成持久状态迁移的显式 tick。

##### 在运行时做什么

它在锁内提供一个时间值与稳定快照，再复用 Bucket 删除和候选发布。

##### 关键代码

```python
self._storage.persist_bucket(candidate)
```

##### 关键语句理解

策略输出本身不改变任何状态。持久化候选才让过期跨重启保存；无 action tick 不必发布。

#### `src/minis3/__init__.py`

??? note "文件差异：src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 3f6e582..36bc1f3 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -1,10 +1,34 @@
     """Public API for the MiniS3 teaching implementation."""
    -from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
    +
    +from .errors import (
    +    BucketAlreadyExists,
    +    BucketNotEmpty,
    +    EntityTooSmall,
    +    InvalidContinuationToken,
    +    InvalidPart,
    +    InvalidPartOrder,
    +    MiniS3Error,
    +    NoSuchBucket,
    +    NoSuchKey,
    +    NoSuchUpload,
    +    NoSuchVersion,
    +    NotModified,
    +    PreconditionFailed,
    +)
     from .bucket import SequenceCounter, VersioningState
    +from .listing import (
    +    ListedObject,
    +    ListedVersion,
    +    ListObjectsResult,
    +    ListObjectVersionsResult,
    +)
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
    +from .lifecycle import (
    +    ExpirationRule,
    +    LifecycleAction,
    +    LifecycleActionKind,
    +    evaluate_expiration,
    +)
    +from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
     from .store import MiniS3
     from .storage import InjectedCrash
    -from .listing import ListedObject, ListedVersion, ListObjectsResult, ListObjectVersionsResult
    -from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder, NoSuchUpload
    -from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
    -from .errors import NotModified, PreconditionFailed
    ```

##### 是什么，为什么现在需要

规则与 action 类型加入公开学习 API。

##### 在运行时做什么

调用方可构造策略、检查返回决策，而不依赖生命周期内部实现。

##### 关键语句理解

包导出声明式值，实际变更仍是 `MiniS3` 操作。

#### `tests/test_lifecycle.py`

??? note "文件差异：tests/test_lifecycle.py"
    ```diff
    diff --git a/tests/test_lifecycle.py b/tests/test_lifecycle.py
    new file mode 100644
    index 0000000..c413345
    --- /dev/null
    +++ b/tests/test_lifecycle.py
    @@ -0,0 +1,110 @@
    +"""Lifecycle rules are pure decisions applied only by an explicit clocked tick."""
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minis3 import (
    +    ExpirationRule,
    +    LifecycleActionKind,
    +    MiniS3,
    +    NoSuchKey,
    +    NoSuchVersion,
    +    VersioningState,
    +    evaluate_expiration,
    +)
    +
    +
    +class ManualClock:
    +    def __init__(self, now: float = 0.0) -> None:
    +        self.now = now
    +
    +    def __call__(self) -> float:
    +        return self.now
    +
    +
    +def test_rule_evaluation_is_pure_prefix_filtered_and_boundary_inclusive(
    +    tmp_path: Path,
    +) -> None:
    +    clock = ManualClock()
    +    store = MiniS3(tmp_path, clock=clock)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", VersioningState.ENABLED)
    +    store.put_object("b", "logs/old", b"old")
    +    store.put_object("b", "keep/old", b"old")
    +    snapshot = store._buckets["b"].records
    +    rule = ExpirationRule("logs", prefix="logs/", expire_current_after=10)
    +
    +    assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
    +    actions = evaluate_expiration(snapshot, [rule], now=10)
    +
    +    assert [(action.key, action.kind) for action in actions] == [
    +        ("logs/old", LifecycleActionKind.EXPIRE_CURRENT)
    +    ]
    +    assert store.get_object("b", "logs/old").body == b"old"
    +
    +
    +def test_tick_expires_current_to_marker_and_noncurrent_physically(
    +    tmp_path: Path,
    +) -> None:
    +    clock = ManualClock()
    +    store = MiniS3(tmp_path, clock=clock)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    old = store.put_object("b", "k", b"old")
    +    clock.now = 5
    +    current = store.put_object("b", "k", b"current")
    +    rule = ExpirationRule(
    +        "expire",
    +        expire_current_after=10,
    +        expire_noncurrent_after=12,
    +    )
    +
    +    clock.now = 12
    +    first_actions = store.lifecycle_tick("b", [rule])
    +    assert [action.kind for action in first_actions] == [
    +        LifecycleActionKind.EXPIRE_NONCURRENT
    +    ]
    +    with pytest.raises(NoSuchVersion):
    +        store.get_object("b", "k", version_id=old.version_id)
    +    assert store.get_object("b", "k") == current
    +
    +    clock.now = 15
    +    second_actions = store.lifecycle_tick("b", [rule])
    +    assert [action.kind for action in second_actions] == [
    +        LifecycleActionKind.EXPIRE_CURRENT
    +    ]
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("b", "k")
    +    history = store.list_object_versions("b").versions
    +    assert history[0].is_delete_marker is True
    +    assert history[1].version_id == current.version_id
    +
    +
    +def test_tick_uses_injected_time_and_persists_timestamps_across_restart(
    +    tmp_path: Path,
    +) -> None:
    +    clock = ManualClock(100)
    +    store = MiniS3(tmp_path, clock=clock)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    version = store.put_object("b", "k", b"value")
    +    assert version.created_at == 100
    +
    +    reopened_clock = ManualClock(109)
    +    reopened = MiniS3(tmp_path, clock=reopened_clock)
    +    rule = ExpirationRule("ten-seconds", expire_current_after=10)
    +    assert reopened.lifecycle_tick("b", [rule]) == ()
    +
    +    reopened_clock.now = 110
    +    assert reopened.lifecycle_tick("b", [rule])[0].kind is (
    +        LifecycleActionKind.EXPIRE_CURRENT
    +    )
    +
    +
    +def test_expiration_rule_rejects_empty_or_negative_policy() -> None:
    +    with pytest.raises(ValueError):
    +        ExpirationRule("empty")
    +    with pytest.raises(ValueError):
    +        ExpirationRule("negative", expire_current_after=-1)
    +
    ```

##### 是什么，为什么现在需要

四条契约覆盖纯过滤/边界、当前与非当前迁移、注入时间/重启和非法规则。

##### 在运行时做什么

`ManualClock` 让测试主动推进时间，证明持久时间戳，而不是等待 wall time。

##### 关键代码

```python
assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
```

##### 关键语句理解

这是刚到阈值前的边界；与 `10.0` 断言成对后，精确证明 inclusive，而不是只测明显过期对象。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/14-lifecycle-tick/tests.txt)`。用例证明纯策略、显式变更、时间注入、重启持久化与规则校验。

### 需要真正记住的内容

纯计算决定、显式 tick 变更、时间可注入、只持久化已应用 action；当前过期建 Marker，非当前过期删除一个历史版本。

### 用自己的话讲清楚

MiniS3 把生命周期策略和执行分开。纯函数根据历史、规则与显式时钟决定 action；带锁 tick 通过已有版本语义应用并发布结果，使时间行为确定且可恢复。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/08-lifecycle.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-13...stage-14)

完成后可运行 `git checkout stage-14` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/14-lifecycle-tick/stage.patch)
