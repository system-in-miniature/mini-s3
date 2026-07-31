# Stage 05 · Version history projection / 版本历史投影

<!-- journey: chapter=3 tests_added=3 -->

## English

### Goal

Expose complete histories so null versions, named versions, and markers remain distinguishable.

### Hands-on task

Starting from stage-04, Implement `list_object_versions(records, prefix=...)` and `MiniS3.list_object_versions`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_versioning.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Current visibility and retained history are different projections of the same record.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`

### The real S3 lesson

Current visibility and retained history are different projections of the same record.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

## 中文

### 目标

公开完整历史，使 null 版本、具名版本与删除标记保持可区分。

### 动手任务

从stage-04开始，实现 `list_object_versions(records, prefix=...)` 与 `MiniS3.list_object_versions`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_versioning.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        当前可见性与保留历史，是同一记录的两种投影。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`

### 对应真实 S3 的一课

当前可见性与保留历史，是同一记录的两种投影。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)
