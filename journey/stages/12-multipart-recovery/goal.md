# Stage 12 · Multipart crash recovery / Multipart 崩溃恢复

<!-- journey: chapter=6 tests_added=2 -->

## English

### Goal

Prove both sides of a completion crash: keep retryable staging before publish, clean it after publish.

### Hands-on task

Starting from stage-11, Exercise `_recover_uploads(...)` with crashes before and after manifest publication. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Mechanism walkthrough

#### Ownership and flow

This test-only stage correlates a published object's `multipart_upload_id` with private staging: retain staging before publish, clean it idempotently after publish.

#### Failure and debugging

After restart, inspect manifest visibility and upload-directory presence as one pair. Either both absent/present in the wrong crash window exposes a recovery bug.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Recovery correlates a published object with its upload ID to make cleanup idempotent.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`

### The real S3 lesson

Recovery correlates a published object with its upload ID to make cleanup idempotent.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

证明完成崩溃的两侧：发布前保留可重试暂存，发布后清理暂存。

### 动手任务

从stage-11开始，用 manifest 发布前后的崩溃测试 `_recover_uploads(...)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `tests/test_storage.py`

### 机制走读

#### 所有权与数据流

这个纯测试 Stage 用已发布对象的 `multipart_upload_id` 关联私有暂存：发布前保留暂存，发布后幂等清理。

#### 失败与排查

重启后把 Manifest 可见性与 Upload 目录存在性成对检查；在错误崩溃窗口同时缺失或同时保留都暴露恢复问题。

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        恢复逻辑用已发布对象的 upload ID 建立关联，使清理具备幂等性。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`

### 对应真实 S3 的一课

恢复逻辑用已发布对象的 upload ID 建立关联，使清理具备幂等性。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
