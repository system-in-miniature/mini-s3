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

### Mechanism walkthrough

#### Ownership and flow

`MiniS3` creates deterministic upload identities, while `DiskStorage` keeps upload metadata and atomically replaced part bytes under private `uploads/` paths outside object manifests.

#### Failure and debugging

Resolve bucket, key, and upload ID together before touching a part. If an unfinished upload appears in GET/listing, inspect whether staging accidentally entered the visible manifest.

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

### 机制走读

#### 所有权与数据流

`MiniS3` 创建确定性 Upload 身份，`DiskStorage` 则把 Upload 元数据和原子替换的 Part 字节放在对象 Manifest 之外的私有 `uploads/` 路径。

#### 失败与排查

写 Part 前同时解析 Bucket、Key 与 Upload ID；若未完成上传出现在 GET/Listing 中，检查暂存内容是否误入可见 Manifest。

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
