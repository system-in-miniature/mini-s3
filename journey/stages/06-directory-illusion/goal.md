# Stage 06 · Listing and the directory illusion / Listing 与目录幻觉

<!-- journey: chapter=4 tests_added=5 -->

## English

### Goal

Derive contents and common prefixes from flat keys, with opaque query-bound pagination tokens.

### Hands-on task

Starting from stage-05, Implement `list_objects(...)`, token encode/decode, and `MiniS3.list_objects(...)`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_listing.py`

### Mechanism walkthrough

#### Ownership and flow

`list_objects` sorts visible flat keys, derives common prefixes at read time, counts prefixes and objects in one page budget, and binds the opaque cursor to the original query.

#### Failure and debugging

Log the sorted candidate stream before pagination. Missing keys usually come from marker filtering; duplicate/shifted pages come from cursor or prefix accounting.

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        S3 directories are a delimiter projection; contents and prefixes share one page budget.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/06-directory-illusion/tests.txt)`

### The real S3 lesson

S3 directories are a delimiter projection; contents and prefixes share one page budget.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/04-listing.md)

## 中文

### 目标

从扁平 Key 推导 contents 与 common prefixes，并加入绑定查询的 opaque 分页 token。

### 动手任务

从stage-05开始，实现 `list_objects(...)`、token 编解码与 `MiniS3.list_objects(...)`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_listing.py`

### 机制走读

#### 所有权与数据流

`list_objects` 排序可见扁平 Key，读取时推导公共前缀，在同一页预算中统计前缀与对象，并把不透明游标绑定到原查询。

#### 失败与排查

分页前先观察排序后的候选流；Key 缺失通常来自删除标记过滤，页面重复或偏移通常来自游标或前缀计数。

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        S3 目录是 delimiter 投影；对象与公共前缀共享同一页额度。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/06-directory-illusion/tests.txt)`

### 对应真实 S3 的一课

S3 目录是 delimiter 投影；对象与公共前缀共享同一页额度。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/04-listing.md)
