# Stage 14 · Deterministic lifecycle expiration / 确定性生命周期过期

<!-- journey: chapter=8 tests_added=4 -->

## English

### Goal

Separate pure expiration decisions from an explicit, injected-clock mutation tick.

### Hands-on task

Starting from stage-13, Implement `ExpirationRule`, `evaluate_expiration(...)`, timestamps, and `MiniS3.lifecycle_tick(...)`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/lifecycle.py`
- `src/minis3/store.py`
- `tests/test_lifecycle.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Lifecycle is deterministic when evaluation is pure and time enters only through the service boundary.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/14-lifecycle-tick/tests.txt)`

### The real S3 lesson

Lifecycle is deterministic when evaluation is pure and time enters only through the service boundary.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/08-lifecycle.md)

## 中文

### 目标

把纯过期决策与显式、注入时钟的变更 tick 分离。

### 动手任务

从stage-13开始，实现 `ExpirationRule`、`evaluate_expiration(...)`、时间戳与 `MiniS3.lifecycle_tick(...)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/lifecycle.py`
- `src/minis3/store.py`
- `tests/test_lifecycle.py`

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
