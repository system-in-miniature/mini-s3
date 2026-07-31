# Stage 09 · Multipart domain and validation / Multipart 领域与校验

<!-- journey: chapter=6 tests_added=0 -->

## English

### Goal

Model upload identity, staged parts, completion manifests, size rules, and composite ETags.

### Hands-on task

Starting from stage-08, Implement `MultipartUpload`, `StagedPart`, receipts, and `validate_completion(...)`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/errors.py`
- `src/minis3/multipart.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Minimum size is checked at completion because only then is the final part known.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`

### The real S3 lesson

Minimum size is checked at completion because only then is the final part known.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

建模上传身份、暂存 Part、完成清单、尺寸规则与组合 ETag。

### 动手任务

从stage-08开始，实现 `MultipartUpload`、`StagedPart`、回执与 `validate_completion(...)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/errors.py`
- `src/minis3/multipart.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        只有完成时才能知道最后一个 Part，因此最小尺寸也在完成时校验。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`

### 对应真实 S3 的一课

只有完成时才能知道最后一个 Part，因此最小尺寸也在完成时校验。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
