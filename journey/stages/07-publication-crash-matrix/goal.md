# Stage 07 · Manifest publication crash matrix / Manifest 发布崩溃矩阵

<!-- journey: chapter=5 tests_added=5 -->

## English

### Goal

Prove the manifest rename is the single visibility boundary by crashing immediately before and after it.

### Deliverable files

- `tests/test_storage.py`

### The problem at this point

Stage 03 described publish-last storage, and clean restarts pass. That is not yet evidence that crashes expose only complete old or complete new states. The claim must be observed at each named crash boundary.

### Test contract

#### See the failure first

One test injects `before_manifest_publish` after new artifacts are durable. Reopening must still return the old object and remove the unreferenced new artifact. If artifact existence alone controls visibility, the new value leaks despite the manifest never committing it.

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### What it is and why it appears

The storage integration suite gains a parameterized crash matrix around artifact and manifest publication.

##### Runtime role

It observes the system only after reopening, which discards misleading in-process memory and exercises recovery cleanup.

##### Key code

```python
crash_injector=CrashOnce("before_manifest_publish"),
```

##### Statement understanding

The named hook fixes the exact interruption boundary. Assertions after a fresh open can therefore distinguish “artifacts durable” from “state published.”

### Basic concepts

A linearization point is the instant a concurrent or recovering observer treats an operation as having taken effect. A crash matrix probes both sides: before the point the old state wins; after the point the complete new state wins. There is no legal half-state.

### Why this mechanism is necessary

Documentation and happy-path tests cannot prove crash atomicity. Deliberate process-like interruption turns publication order into executable evidence and prevents a future refactor from moving visibility to artifact creation accidentally.

### Runtime mental model

The test prepares old state, installs `CrashOnce`, attempts a mutation, catches `InjectedCrash`, and constructs a fresh service. It then checks visible data and disk debris. The production code does not change in this stage; the new value is confidence in the existing boundary.

### Mechanism blocks

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`. Five added cases cover multiple pre-publication points plus the post-publication side and cleanup.

### Durable takeaways

Artifact durability does not equal visibility. The manifest rename is the commit point: before it recovery selects old state, after it recovery selects complete new state.

### Explain it in your own words

The crash matrix proves atomicity by killing the operation on both sides of one named boundary and reopening from disk. Only the manifest makes immutable artifacts visible, so unreferenced files before publication are debris, while a published manifest after rename commits the complete new value.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

## 中文

### 目标

在 Manifest rename 前后立即崩溃，证明它是唯一可见性边界。

### 交付文件

- `tests/test_storage.py`

### 当前遇到的问题

Stage 03 描述了最后发布的存储，正常重启也通过了，但这还不能证明崩溃只会暴露完整旧状态或完整新状态。必须在每个命名崩溃边界实际观察。

### 测试契约

#### 先看会坏在哪里

一条测试在新 Artifact 已持久化后注入 `before_manifest_publish`。重开后必须仍返回旧对象并删除未引用的新 Artifact。如果 Artifact 只要存在就算可见，新值会在 Manifest 从未提交时泄漏。

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### 是什么，为什么现在需要

存储集成套件加入围绕 Artifact 与 Manifest 发布的参数化崩溃矩阵。

##### 在运行时做什么

它只在重开后观察系统，丢弃可能误导人的进程内内存，并实际运行恢复清理。

##### 关键代码

```python
crash_injector=CrashOnce("before_manifest_publish"),
```

##### 关键语句理解

命名 hook 固定精确中断边界；全新实例上的断言因而能区分“Artifact 已持久化”和“状态已发布”。

### 基本概念

线性化点是并发或恢复观察者认为操作已经生效的瞬间。崩溃矩阵探测它两侧：点之前旧状态获胜，点之后完整新状态获胜，不允许半状态。

### 为什么需要这个机制

文档和 happy path 无法证明崩溃原子性。故意中断把发布顺序变成可执行证据，也防止未来重构误把可见性移动到 Artifact 创建时。

### 运行时心智模型

测试准备旧状态、安装 `CrashOnce`、尝试变更、捕获 `InjectedCrash`，再创建全新服务。随后检查可见数据与磁盘残留。本 Stage 不改生产代码，新增的是对现有边界的可信证据。

### 机制板块

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`。五个新增用例覆盖多个发布前点、发布后侧与清理。

### 需要真正记住的内容

Artifact 持久化不等于可见。Manifest rename 是提交点：此前恢复选择旧状态，此后恢复选择完整新状态。

### 用自己的话讲清楚

崩溃矩阵通过在线性化点两侧中断并从磁盘重开来证明原子性。只有 Manifest 能让不可变 Artifact 可见，所以发布前未引用文件只是残留，rename 后已发布 Manifest 则提交完整新值。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)
