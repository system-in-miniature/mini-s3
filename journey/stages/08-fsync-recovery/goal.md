# Stage 08 · Directory fsync and startup cleanup / 目录 fsync 与启动清理

<!-- journey: chapter=5 tests_added=3 -->

## English

### Goal

Verify directory-entry durability and recovery cleanup for temporary and unreferenced crash debris.

### Deliverable files

- `tests/test_storage.py`

### The problem at this point

The crash matrix proves which manifest is visible, but durability also depends on directory entries. Creating nested directories or renaming a file without fsyncing the right parent can make a correct-looking run disappear after power loss. Recovery must also remove debris without deleting referenced artifacts.

### Failure preview

The parent-chain contract records fsync calls while creating `one/two/three`. It expects calls for the existing root and each newly created directory's parent. If only the final directory is fsynced, one missing ancestor entry can make the whole subtree unreachable after restart.

### Basic concepts

A directory stores name-to-inode mappings. Persisting file contents does not automatically persist creation or rename of that name. Cleanup classifies files by authority: temporary names and unreferenced artifacts may be removed; manifest-referenced artifacts must remain.

### Why this mechanism is necessary

Crash safety is an end-to-end ordering property, not merely a call to `fsync` somewhere. Recording the exact parent chain and exercising cleanup protects the subtle filesystem assumptions that ordinary object assertions cannot see.

### Runtime mental model

Tests replace `fsync_directory` with a recorder, perform real directory/storage creation, and assert the ordered parents. A separate restart case plants a stray temporary file, reopens storage, and requires cleanup while the published object remains readable.

### File-by-file walkthrough

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### What it is and why it appears

The storage suite now inspects durability calls and startup hygiene, not just logical object values.

##### Runtime role

Its recorder makes invisible filesystem obligations observable; its restart case verifies cleanup decisions against manifest authority.

##### Key code

```python
assert calls == [tmp_path, tmp_path / "one", tmp_path / "one" / "two"]
```

##### Statement understanding

Each new directory entry lives in its parent, so the expected list walks the ancestry rather than repeating the final path. This assertion locks the durability chain.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`. Three cases prove parent-chain fsync behavior for atomic writes and Bucket creation plus safe removal of stray temporary files.

### Durable takeaways

File bytes, file names, and directory trees have separate durability obligations. Recovery removes what is not authoritative, never what the manifest still references.

### Explain it in your own words

MiniS3 makes publication survive power loss by fsyncing every parent whose directory entries changed. On startup it treats the manifest as authority, preserving referenced immutable artifacts and deleting temporary or orphaned debris left by interrupted work.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

## 中文

### 目标

验证目录项持久性，以及启动时对临时和未引用崩溃残留的清理。

### 交付文件

- `tests/test_storage.py`

### 当前遇到的问题

崩溃矩阵证明了哪个 Manifest 可见，但持久性还依赖目录项。创建嵌套目录或 rename 后没有 fsync 正确父目录，当前看似正确的运行可能在掉电后消失。恢复还必须清理残留，同时不能删除被引用 Artifact。

### 先看会坏在哪里

父链契约在创建 `one/two/three` 时记录 fsync，要求现有根目录和每个新目录的父级都出现。若只 fsync 最后一层，一个缺失的祖先目录项就可能让整棵子树在重启后不可达。

### 基本概念

目录保存名称到 inode 的映射。持久化文件内容不会自动持久化这个名称的创建或 rename。清理依据权威分类：临时名称和未引用 Artifact 可删除；Manifest 引用的 Artifact 必须保留。

### 为什么需要这个机制

崩溃安全是端到端顺序属性，不是“某处调用了 fsync”就够。记录精确父链并运行清理，能保护普通对象断言看不到的文件系统假设。

### 运行时心智模型

测试用 recorder 替换 `fsync_directory`，执行真实目录/存储创建，再断言父级顺序。另一个重启场景植入 stray 临时文件，重开存储后要求清理它，同时已发布对象仍可读取。

### 逐文件走读

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### 是什么，为什么现在需要

存储套件现在检查持久化调用与启动卫生，而不只检查逻辑对象值。

##### 在运行时做什么

Recorder 让不可见的文件系统义务变得可观察；重启场景按 Manifest 权威验证清理决策。

##### 关键代码

```python
assert calls == [tmp_path, tmp_path / "one", tmp_path / "one" / "two"]
```

##### 关键语句理解

每个新目录项存放在其父目录中，因此期望列表沿祖先链前进，而不是重复最终路径。这条断言锁定持久化链。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`。三个用例证明 atomic write、Bucket 创建的父链 fsync，以及安全删除 stray 临时文件。

### 需要真正记住的内容

文件字节、文件名和目录树各有持久化义务。恢复删除不权威内容，但绝不能删除 Manifest 仍引用的内容。

### 用自己的话讲清楚

MiniS3 通过 fsync 每个发生目录项变化的父目录，让发布跨掉电保存。启动时以 Manifest 为权威，保留被引用的不可变 Artifact，清除中断工作留下的临时或孤儿残留。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)
