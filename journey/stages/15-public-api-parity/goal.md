# Stage 15 · Public API and parity closeout / 公开 API 与守链收官

<!-- journey: chapter=9 tests_added=0 -->

## English

### Goal

Expose the complete teaching API and prove the reconstructed source and Journey-owned tests equal main byte for byte.

### Hands-on task

Starting from stage-14, Finalize `minis3.__init__` exports and run the complete 49-test contract. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`

### Mechanism walkthrough

#### Ownership and flow

`minis3.__init__` is the supported adapter surface; the Journey builder then applies every patch and compares final `src/minis3` plus Journey-owned tests byte for byte with main. Site-only documentation tests stay outside this rebuild contract.

#### Failure and debugging

An import failure belongs to export wiring; a final parity failure names missing, extra, or changed files and must be fixed in the stage chain rather than hidden in generated commits.

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

公开完整教学 API，并证明重建后的源码与 Journey 所有的测试逐字节等于 main。

### 动手任务

从stage-14开始，完成 `minis3.__init__` 导出，并运行完整 49 项测试契约。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`

### 机制走读

#### 所有权与数据流

`minis3.__init__` 是受支持的适配器接口；Journey Builder 随后应用全部 Patch，并把最终 `src/minis3` 与 Journey 所有的测试和 main 逐字节比较。仅服务网站的文档测试不属于重建契约。

#### 失败与排查

导入失败属于导出接线问题；最终 Parity 失败会列出缺失、多余或变化文件，必须修复 Stage 链，不能藏在生成 Commit 中。

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
