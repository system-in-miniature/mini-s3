# Stage 08 · Directory fsync and startup cleanup / 目录 fsync 与启动清理

<!-- journey: chapter=5 tests_added=3 -->

## English

### Goal

Verify parent-directory durability and remove temporary or unreferenced crash debris on startup.

### Hands-on task

Starting from stage-07, Harden and test `atomic_write`, `durable_mkdir`, `DiskStorage.load_buckets`, and cleanup paths. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Atomic rename is not durable publication until the containing directory is fsynced.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`

### The real S3 lesson

Atomic rename is not durable publication until the containing directory is fsynced.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

## 中文

### 目标

验证父目录持久性，并在启动时清理临时或未引用的崩溃残留。

### 动手任务

从stage-07开始，强化并测试 `atomic_write`、`durable_mkdir`、`DiskStorage.load_buckets` 与清理路径。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `tests/test_storage.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        只有对所在目录执行 fsync，原子 rename 才成为持久发布。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`

### 对应真实 S3 的一课

只有对所在目录执行 fsync，原子 rename 才成为持久发布。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)
