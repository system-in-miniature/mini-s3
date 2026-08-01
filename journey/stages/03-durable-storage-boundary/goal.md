# Stage 03 · Durable storage boundary / 持久化存储边界

<!-- journey: chapter=5 tests_added=1 -->

## English

### Goal

Give buckets a durable manifest and immutable object artifacts behind one storage owner.

### Hands-on task

Starting from stage-02, Implement `DiskStorage`, `atomic_write`, `durable_mkdir`, and recovery-oriented path helpers. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/storage/__init__.py`
- `src/minis3/storage/atomic.py`
- `src/minis3/storage/disk.py`
- `tests/test_storage_boundary.py`

### Mechanism walkthrough

#### Ownership and flow

`DiskStorage` writes immutable data/metadata artifacts first and publishes `manifest.json` last. `atomic_write` makes rename the visibility point and fsync makes directory entries durable.

#### Failure and debugging

Trace artifact path, temporary name, rename, and parent fsync in order. On restart, compare manifest references with recovered files; unreferenced artifacts must not become visible.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        A manifest names visible immutable artifacts; publication order defines visibility.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`

### The real S3 lesson

A manifest names visible immutable artifacts; publication order defines visibility.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

## 中文

### 目标

让 Bucket 通过单一存储所有者拥有持久 manifest 与不可变对象制品。

### 动手任务

从stage-02开始，实现 `DiskStorage`、`atomic_write`、`durable_mkdir` 与面向恢复的路径辅助函数。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/storage/__init__.py`
- `src/minis3/storage/atomic.py`
- `src/minis3/storage/disk.py`

### 机制走读

#### 所有权与数据流

`DiskStorage` 先写不可变数据与元数据 Artifact，最后发布 `manifest.json`；`atomic_write` 让 rename 成为可见性点，fsync 让目录项持久化。

#### 失败与排查

按 Artifact 路径、临时名、rename、父目录 fsync 的顺序追踪；重启时对照 Manifest 引用与恢复文件，未引用 Artifact 不能变得可见。

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        manifest 引用可见的不可变制品；发布顺序决定可见性。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`

### 对应真实 S3 的一课

manifest 引用可见的不可变制品；发布顺序决定可见性。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)
