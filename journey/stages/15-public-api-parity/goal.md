# Stage 15 · Public API and parity closeout / 公开 API 与守链收官

<!-- journey: chapter=9 tests_added=0 -->

## English

### Goal

Expose the complete teaching API and prove the reconstructed source and tests equal main byte for byte.

### Hands-on task

Starting from stage-14, Finalize `minis3.__init__` exports and run the complete 49-test contract. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        A rebuild journey stays trustworthy only when CI guards both behavior and final-source parity.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)`

### The real S3 lesson

A rebuild journey stays trustworthy only when CI guards both behavior and final-source parity.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/09-methodology.md)

## 中文

### 目标

公开完整教学 API，并证明重建后的源码与测试逐字节等于 main。

### 动手任务

从stage-14开始，完成 `minis3.__init__` 导出，并运行完整 49 项测试契约。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        只有 CI 同时守护行为与最终源码一致性，重建旅程才可信。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)`

### 对应真实 S3 的一课

只有 CI 同时守护行为与最终源码一致性，重建旅程才可信。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/09-methodology.md)
