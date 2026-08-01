# Stage 02 · Bucket 状态与确定性 ID

### 目标

引入 Bucket 聚合、合法版本化迁移，以及可注入的单调序列。

### 动手任务

从stage-01开始，实现 `VersioningState`、`SequenceCounter` 与 `Bucket.set_versioning(state)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/bucket.py`

### 机制走读

#### 所有权与数据流

`Bucket` 拥有每个 Key 的历史与合法版本状态迁移；注入的 `SequenceCounter` 为每次 PUT 或删除标记生成确定性的公开与内部身份。

#### 失败与排查

先看分支前的 Bucket 状态，再比较变更后的 `version_id`、`storage_id` 与记录顺序；非法迁移必须在修改状态前失败。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/bucket.py`

拥有 Bucket 内部状态迁移的聚合。

由 `MiniS3` 调用；把一次命令和当前记录转换为下一份内存历史。

**变化锚点:** `VersioningState`, `SequenceCounter`, `__init__`, `__call__`, `ensure_at_least`, `Bucket`, `set_versioning`, `put`, `get`, `delete`

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

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        版本化可启用、可暂停，但不能回到从未启用状态。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`

### 对应真实 S3 的一课

版本化可启用、可暂停，但不能回到从未启用状态。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-01...stage-02)

完成后可运行 `git checkout stage-02` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/02-bucket-state/stage.patch)
