# Stage 14 · 确定性生命周期过期

### 目标

把纯过期决策与显式、注入时钟的变更 tick 分离。

### 动手任务

从stage-13开始，实现 `ExpirationRule`、`evaluate_expiration(...)`、时间戳与 `MiniS3.lifecycle_tick(...)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/lifecycle.py`
- `src/minis3/store.py`
- `tests/test_lifecycle.py`

### 机制走读

#### 所有权与数据流

`evaluate_expiration` 是针对带时间戳版本的纯策略；`MiniS3.lifecycle_tick` 注入时间、在锁内执行动作并持久化结果历史。

#### 失败与排查

先单独运行纯评估器；候选错误属于策略或时间问题，动作正确但存储状态错误属于变更或持久化问题。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/lifecycle.py`

纯生命周期过期策略。

由 `MiniS3` 作为策略函数调用；接收显式值并返回由服务执行的决策。

**变化锚点:** `ExpirationRule`, `__post_init__`, `LifecycleActionKind`, `LifecycleAction`, `_old_enough`, `evaluate_expiration`

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

#### `src/minis3/store.py`

协调领域逻辑与持久化的应用服务。

接收公开调用，拥有加锁与编排，再委托给领域、投影和存储边界。

**变化锚点:** `lifecycle_tick`

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

#### `src/minis3/__init__.py`

受支持的包级公开接口。

由用户导入触达；接线错误会在运行时流程开始前表现为名称缺失。

**变化锚点:** 配置、导出或文档变化

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

#### `tests/test_lifecycle.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `ManualClock`, `__init__`, `__call__`, `test_rule_evaluation_is_pure_prefix_filtered_and_boundary_inclusive`, `test_tick_expires_current_to_marker_and_noncurrent_physically`, `test_tick_uses_injected_time_and_persists_timestamps_across_restart`, `test_expiration_rule_rejects_empty_or_negative_policy`

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

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        当评估保持纯函数、时间只从服务边界注入时，生命周期行为才可确定复现。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/14-lifecycle-tick/tests.txt)`

### 对应真实 S3 的一课

当评估保持纯函数、时间只从服务边界注入时，生命周期行为才可确定复现。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/08-lifecycle.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-13...stage-14)

完成后可运行 `git checkout stage-14` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/14-lifecycle-tick/stage.patch)
