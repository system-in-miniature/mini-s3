# Stage 07 · Manifest publication crash matrix / Manifest 发布崩溃矩阵

<!-- journey: chapter=5 tests_added=5 -->

## English

### Goal

Pin the manifest rename as the linearization point by crashing immediately before and after it.

### Hands-on task

Starting from stage-06, Exercise `DiskStorage.persist_bucket` through `CrashOnce` at every publication boundary. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Mechanism walkthrough

#### Ownership and flow

This stage changes tests, not production code. Fault injection brackets manifest replacement to prove the old/new visibility split around one linearization point.

#### Failure and debugging

Reopen storage after each injected crash and inspect only published state. Seeing partial new state means publication order or recovery trust boundaries are wrong.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Before rename, recovery sees the old state; after rename, it sees the complete new state.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`

### The real S3 lesson

Before rename, recovery sees the old state; after rename, it sees the complete new state.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

## 中文

### 目标

在 manifest rename 前后注入崩溃，钉死其线性化点。

### 动手任务

从stage-06开始，通过 `CrashOnce` 覆盖 `DiskStorage.persist_bucket` 的每个发布边界。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `tests/test_storage.py`

### 机制走读

#### 所有权与数据流

本阶段只修改测试，不修改生产代码；故障注入包围 Manifest 替换，以证明单一线性化点两侧的旧/新可见性分界。

#### 失败与排查

每次注入崩溃后重新打开存储，只观察已发布状态；若看到部分新状态，说明发布顺序或恢复信任边界错误。

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        rename 前恢复到旧状态；rename 后看到完整新状态。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`

### 对应真实 S3 的一课

rename 前恢复到旧状态；rename 后看到完整新状态。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)
