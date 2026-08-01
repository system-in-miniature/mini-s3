# Stage 02 · Bucket state and deterministic IDs / Bucket 状态与确定性 ID

<!-- journey: chapter=3 tests_added=1 -->

## English

### Goal

Introduce the bucket aggregate, legal versioning transitions, and an injectable monotonic sequence.

### Hands-on task

Starting from stage-01, Implement `VersioningState`, `SequenceCounter`, and `Bucket.set_versioning(state)`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/bucket.py`
- `tests/test_bucket.py`

### Mechanism walkthrough

#### Ownership and flow

`Bucket` owns per-key history and legal versioning transitions. An injected `SequenceCounter` turns each PUT or marker into deterministic public and internal identities.

#### Failure and debugging

Inspect the bucket state before the branch, then compare `version_id`, `storage_id`, and record order after it. Illegal transitions should fail before mutating state.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Versioning can be enabled and suspended, but never reset to the never-enabled state.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`

### The real S3 lesson

Versioning can be enabled and suspended, but never reset to the never-enabled state.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

## 中文

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
