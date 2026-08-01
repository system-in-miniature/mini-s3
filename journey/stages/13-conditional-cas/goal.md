# Stage 13 · Conditional requests and CAS / 条件请求与 CAS

<!-- journey: chapter=7 tests_added=4 -->

## English

### Goal

Turn ETags into cache validators and serialized compare-and-swap preconditions.

### Hands-on task

Starting from stage-12, Implement ETag matching plus `if_match`/`if_none_match` on object operations while holding `_lock`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/conditional.py`
- `src/minis3/errors.py`
- `src/minis3/store.py`
- `tests/test_conditional.py`

### Mechanism walkthrough

#### Ownership and flow

Pure helpers evaluate ETag syntax; `MiniS3` holds one lock across reading the current visible ETag, checking the precondition, and publishing the mutation.

#### Failure and debugging

Separate matching errors from serialization errors. If two conditional writers both win, comparison and mutation escaped the same critical section.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        The comparison and publication must share one critical section or two writers can both win.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`

### The real S3 lesson

The comparison and publication must share one critical section or two writers can both win.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/07-conditional.md)

## 中文

### 目标

把 ETag 变成缓存校验器与串行化的 compare-and-swap 前置条件。

### 动手任务

从stage-12开始，实现 ETag 匹配，并在持有 `_lock` 时处理对象操作的 `if_match`/`if_none_match`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/conditional.py`
- `src/minis3/errors.py`
- `src/minis3/store.py`
- `tests/test_conditional.py`

### 机制走读

#### 所有权与数据流

纯辅助函数评估 ETag 语法；`MiniS3` 用同一把锁覆盖读取当前可见 ETag、检查前置条件和发布变更。

#### 失败与排查

区分匹配语义问题与串行化问题；若两个条件写者都成功，说明比较与变更没有处于同一临界区。

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        比较与发布必须处于同一临界区，否则两个写者都可能成功。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`

### 对应真实 S3 的一课

比较与发布必须处于同一临界区，否则两个写者都可能成功。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/07-conditional.md)
