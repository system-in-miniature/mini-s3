# Stage 02 · Bucket 状态与确定性 ID

### 目标

引入 Bucket 聚合、合法版本化迁移与确定性身份。

### 交付文件

- `src/minis3/bucket.py`
- `tests/test_bucket.py`

### 当前遇到的问题

Stage 01 只能描述一份值，还不能决定已有历史上的 PUT 或 DELETE 应该做什么。这些规则必须由同一个边界拥有，否则服务、存储和 Listing 可能各自实现不同的版本化语义。

### 先看会坏在哪里

聚合契约先写入未版本化值，再启用版本化、再次写入、暂停版本化，最后尝试回到 `UNVERSIONED`。如果最后一步成功，已存在的具名历史会被误解释为“从未启用版本化”。预期的 `ValueError` 在引入持久化以前就锁定状态机。

### 基本概念

聚合是相关状态迁移的所有者。这里一个 `Bucket` 同时拥有版本化状态与每个 Key 的 `ObjectRecord`。`UNVERSIONED` 表示从未启用；`SUSPENDED` 表示曾经启用，之后新写入使用公开 `null` 槽，但具名历史仍保留。

公开 `version_id` 与内部 `storage_id` 解决不同问题。暂停状态可以反复使用公开 ID `null`，但不可变磁盘 Artifact 仍需要唯一内部名称。注入的单调序列可复现地生成两者。

### 为什么需要这个机制

如果分支散落在调用方，非法迁移和替换规则很容易不一致。集中到 Bucket 后，PUT、GET、DELETE 共用一套历史模型。确定性 ID 还让恢复逻辑能从最大已发布序列继续，而不是依赖随机值。

### 运行时心智模型

调用方给出命令和 `SequenceCounter`。Bucket 校验状态、取一个序列、构造新版本或 Marker，再替换精确 Key 的不可变 `ObjectRecord`。Enabled 写入追加历史；未版本化和暂停写入只替换 `null` 槽。

### 逐文件走读

#### `src/minis3/bucket.py`

##### 是什么，为什么现在需要

这个可变聚合是合法版本状态与每 Key 历史的唯一所有者，持久化仍留在外部。

##### 在运行时做什么

服务层会调用 `set_versioning`、`put`、`get`、`delete`。每个方法把当前 Bucket 状态变成下一状态，或者在变更前抛错。

##### 关键代码

```python
if self.versioning is VersioningState.ENABLED:
    versions = (version, *old.versions)
else:
```

##### 关键语句理解

Enabled PUT 通过前插保留全部旧版本；`else` 则替换公开 `null` 槽并保留具名历史。把两个分支写成一样会破坏暂停语义。

??? note "文件差异：src/minis3/bucket.py"
    ```diff
    diff --git a/src/minis3/bucket.py b/src/minis3/bucket.py
    new file mode 100644
    index 0000000..b0a46e5
    --- /dev/null
    +++ b/src/minis3/bucket.py
    @@ -0,0 +1,159 @@
    +"""Bucket ownership and the versioning state machine.
    +
    +The important distinction is between the public version id and an internal
    +storage id. A suspended bucket repeatedly writes public version ``"null"``,
    +but every write still receives a unique storage id so durable publication can
    +refer to immutable files.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable
    +from dataclasses import dataclass, field
    +from enum import StrEnum
    +
    +from .errors import NoSuchKey, NoSuchVersion
    +from .model import (
    +    NULL_VERSION_ID,
    +    DeleteMarker,
    +    ObjectRecord,
    +    ObjectVersion,
    +    Version,
    +    content_etag,
    +)
    +
    +
    +class VersioningState(StrEnum):
    +    """The three bucket versioning states visible in M1."""
    +
    +    UNVERSIONED = "unversioned"
    +    ENABLED = "enabled"
    +    SUSPENDED = "suspended"
    +
    +
    +class SequenceCounter:
    +    """Injectable deterministic sequence source; random ids are forbidden."""
    +
    +    def __init__(self, start: int = 1) -> None:
    +        if start < 1:
    +            raise ValueError("counter start must be positive")
    +        self._next_value = start
    +
    +    def __call__(self) -> int:
    +        value = self._next_value
    +        self._next_value += 1
    +        return value
    +
    +    def ensure_at_least(self, value: int) -> None:
    +        """Advance a default counter beyond sequences recovered from disk."""
    +
    +        self._next_value = max(self._next_value, value)
    +
    +
    +@dataclass(slots=True)
    +class Bucket:
    +    """Mutable aggregate for one bucket; persistence is coordinated by Store."""
    +
    +    name: str
    +    versioning: VersioningState = VersioningState.UNVERSIONED
    +    records: dict[str, ObjectRecord] = field(default_factory=dict)
    +
    +    def set_versioning(self, state: VersioningState | str) -> None:
    +        state = VersioningState(state)
    +        if state is VersioningState.UNVERSIONED and self.versioning is not state:
    +            raise ValueError("versioning cannot return to unversioned after it is enabled")
    +        if (
    +            self.versioning is VersioningState.UNVERSIONED
    +            and state is VersioningState.SUSPENDED
    +        ):
    +            raise ValueError("versioning must be enabled before it can be suspended")
    +        self.versioning = state
    +
    +    def put(self, key: str, body: bytes, next_sequence: Callable[[], int]) -> Version:
    +        sequence = next_sequence()
    +        version_id = (
    +            f"v{sequence:08d}"
    +            if self.versioning is VersioningState.ENABLED
    +            else NULL_VERSION_ID
    +        )
    +        version = Version(
    +            version_id=version_id,
    +            storage_id=f"e{sequence:08d}",
    +            sequence=sequence,
    +            body=bytes(body),
    +            etag=content_etag(body),
    +        )
    +        old = self.records.get(key, ObjectRecord(key))
    +
    +        if self.versioning is VersioningState.ENABLED:
    +            versions = (version, *old.versions)
    +        else:
    +            # Unversioned and suspended writes replace only the null slot. In
    +            # suspended state, named historical versions remain reachable.
    +            retained = tuple(
    +                item for item in old.versions if item.version_id != NULL_VERSION_ID
    +            )
    +            versions = (version, *retained)
    +        self.records[key] = ObjectRecord(key, versions)
    +        return version
    +
    +    def get(self, key: str, version_id: str | None = None) -> Version:
    +        record = self.records.get(key)
    +        if record is None or not record.versions:
    +            raise NoSuchKey(key)
    +
    +        if version_id is None:
    +            candidate = record.versions[0]
    +            if isinstance(candidate, DeleteMarker):
    +                raise NoSuchKey(key)
    +            return candidate
    +
    +        for candidate in record.versions:
    +            if candidate.version_id == version_id:
    +                if isinstance(candidate, DeleteMarker):
    +                    raise NoSuchKey(key)
    +                return candidate
    +        raise NoSuchVersion(f"{key}:{version_id}")
    +
    +    def delete(
    +        self,
    +        key: str,
    +        next_sequence: Callable[[], int],
    +        version_id: str | None = None,
    +    ) -> ObjectVersion | None:
    +        record = self.records.get(key)
    +
    +        if version_id is not None:
    +            if record is None:
    +                raise NoSuchVersion(f"{key}:{version_id}")
    +            for index, candidate in enumerate(record.versions):
    +                if candidate.version_id == version_id:
    +                    remaining = record.versions[:index] + record.versions[index + 1 :]
    +                    if remaining:
    +                        self.records[key] = ObjectRecord(key, remaining)
    +                    else:
    +                        self.records.pop(key)
    +                    return candidate
    +            raise NoSuchVersion(f"{key}:{version_id}")
    +
    +        has_named_history = record is not None and any(
    +            item.version_id != NULL_VERSION_ID for item in record.versions
    +        )
    +        if self.versioning is VersioningState.UNVERSIONED and not has_named_history:
    +            self.records.pop(key, None)
    +            return None
    +
    +        sequence = next_sequence()
    +        marker_id = (
    +            f"v{sequence:08d}"
    +            if self.versioning is VersioningState.ENABLED
    +            else NULL_VERSION_ID
    +        )
    +        marker = DeleteMarker(marker_id, f"e{sequence:08d}", sequence)
    +        old_versions = () if record is None else record.versions
    +        if self.versioning is VersioningState.SUSPENDED or has_named_history:
    +            old_versions = tuple(
    +                item for item in old_versions if item.version_id != NULL_VERSION_ID
    +            )
    +        self.records[key] = ObjectRecord(key, (marker, *old_versions))
    +        return marker
    ```

#### `tests/test_bucket.py`

##### 是什么，为什么现在需要

这个契约先单测聚合，避免服务层和磁盘层掩盖错误来源。

##### 在运行时做什么

它证明相同序列源依次产生 `null/e00000001` 与 `v00000002/e00000002`，并锁定禁止的倒退迁移。

##### 关键代码

```python
with pytest.raises(ValueError):
    bucket.set_versioning(VersioningState.UNVERSIONED)
```

##### 关键语句理解

这个失败属于领域行为：一旦可能存在具名版本，“从未版本化”就不再是真实状态。

??? note "文件差异：tests/test_bucket.py"
    ```diff
    diff --git a/tests/test_bucket.py b/tests/test_bucket.py
    new file mode 100644
    index 0000000..139fcf0
    --- /dev/null
    +++ b/tests/test_bucket.py
    @@ -0,0 +1,21 @@
    +"""Focused contracts for the bucket aggregate before service wiring."""
    +
    +import pytest
    +
    +from minis3.bucket import Bucket, SequenceCounter, VersioningState
    +
    +
    +def test_bucket_owns_versioning_transitions_and_deterministic_ids() -> None:
    +    bucket = Bucket("b")
    +    counter = SequenceCounter()
    +
    +    null = bucket.put("key", b"before", counter)
    +    bucket.set_versioning(VersioningState.ENABLED)
    +    named = bucket.put("key", b"after", counter)
    +    bucket.set_versioning(VersioningState.SUSPENDED)
    +
    +    assert (null.version_id, null.storage_id) == ("null", "e00000001")
    +    assert (named.version_id, named.storage_id) == ("v00000002", "e00000002")
    +    assert bucket.get("key").body == b"after"
    +    with pytest.raises(ValueError):
    +        bucket.set_versioning(VersioningState.UNVERSIONED)
    ```

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`。它证明聚合迁移与身份契约，但还不证明磁盘恢复或并发服务调用。

### 需要真正记住的内容

Bucket 拥有历史迁移；公开版本身份与内部 Artifact 身份分离；Enabled 与 Suspended 不能混为一谈。

### 用自己的话讲清楚

Bucket 聚合阻止每个调用方自行发明版本化规则。它用确定性序列排序变更，在需要时保留具名历史，并拒绝会让现有历史无法解释的状态迁移。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-01...stage-02)

完成后可运行 `git checkout stage-02` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/02-bucket-state/stage.patch)
