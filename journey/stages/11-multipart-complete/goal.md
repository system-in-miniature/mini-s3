# Stage 11 · Atomic multipart completion / Multipart 原子完成

<!-- journey: chapter=6 tests_added=4 -->

## English

### Goal

Validate an ordered client manifest, assemble bytes, and publish exactly one visible object.

### Hands-on task

Starting from stage-10, Implement `MiniS3.complete_multipart_upload(...)` and connect composite ETags to `Bucket.put(...)`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/store.py`
- `tests/test_multipart.py`

### Mechanism walkthrough

#### Ownership and flow

Completion loads private parts, validates the ordered client manifest, concatenates bytes, publishes once through normal `Bucket.put`, then removes staging.

#### Failure and debugging

Inspect validation before assembly and manifest publication before cleanup. A visible partial object means publication was split; lost retry state means cleanup happened too early.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Completion becomes visible only through the same bucket-manifest publication boundary as PUT.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`

### The real S3 lesson

Completion becomes visible only through the same bucket-manifest publication boundary as PUT.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

校验有序客户端清单、组装字节，并只发布一个可见对象。

### 动手任务

从stage-10开始，实现 `MiniS3.complete_multipart_upload(...)`，并把组合 ETag 接入 `Bucket.put(...)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/store.py`
- `tests/test_multipart.py`

### 机制走读

#### 所有权与数据流

完成操作加载私有 Part、校验有序客户端清单、拼接字节，通过普通 `Bucket.put` 只发布一次，最后删除暂存。

#### 失败与排查

先检查组装前校验，再检查清理前 Manifest 发布；出现部分可见对象说明发布被拆开，丢失重试状态说明清理过早。

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        完成操作只通过与 PUT 相同的 Bucket manifest 发布边界变为可见。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`

### 对应真实 S3 的一课

完成操作只通过与 PUT 相同的 Bucket manifest 发布边界变为可见。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
