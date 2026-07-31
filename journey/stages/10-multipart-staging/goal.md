# Stage 10 · Durable multipart staging / Multipart 持久暂存

<!-- journey: chapter=6 tests_added=1 -->

## English

### Goal

Persist invisible uploads and replace parts atomically without creating object records.

### Hands-on task

Starting from stage-09, Implement create/load/write/remove upload methods and `MiniS3.create_multipart_upload`, `upload_part`, `abort_multipart_upload`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/bucket.py`
- `src/minis3/model.py`
- `src/minis3/storage/disk.py`
- `src/minis3/store.py`
- `tests/test_multipart.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        An unfinished upload lives outside the visible object manifest.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/10-multipart-staging/tests.txt)`

### The real S3 lesson

An unfinished upload lives outside the visible object manifest.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

持久化不可见上传，并原子替换 Part，而不创建对象记录。

### 动手任务

从stage-09开始，实现上传 create/load/write/remove 方法，以及对应的 `MiniS3` 三个入口。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/bucket.py`
- `src/minis3/model.py`
- `src/minis3/storage/disk.py`
- `src/minis3/store.py`
- `tests/test_multipart.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        未完成上传位于可见对象 manifest 之外。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/10-multipart-staging/tests.txt)`

### 对应真实 S3 的一课

未完成上传位于可见对象 manifest 之外。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
