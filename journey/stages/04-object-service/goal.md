# Stage 04 · Object service facade / 对象服务门面

<!-- journey: chapter=2 tests_added=15 -->

## English

### Goal

Join buckets and storage through a locked service that supports versioned PUT, GET, HEAD, and DELETE.

### Hands-on task

Starting from stage-03, Implement `MiniS3.__init__`, bucket operations, object operations, and `_bucket(name)`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/store.py`
- `tests/test_storage.py`
- `tests/test_versioning.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Strong consistency comes from one mutation lock plus publish-before-swap candidate state.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/04-object-service/tests.txt)`

### The real S3 lesson

Strong consistency comes from one mutation lock plus publish-before-swap candidate state.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/02-objects-etag.md)

## 中文

### 目标

用加锁服务连接 Bucket 与存储，支持版本化 PUT、GET、HEAD 与 DELETE。

### 动手任务

从stage-03开始，实现 `MiniS3.__init__`、Bucket 操作、对象操作与 `_bucket(name)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/store.py`
- `tests/test_storage.py`
- `tests/test_versioning.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        强一致性来自单一变更锁，以及先发布再替换候选状态。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/04-object-service/tests.txt)`

### 对应真实 S3 的一课

强一致性来自单一变更锁，以及先发布再替换候选状态。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/02-objects-etag.md)
