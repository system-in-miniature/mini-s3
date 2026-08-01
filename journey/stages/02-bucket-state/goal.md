# Stage 02 · Bucket state and deterministic IDs / Bucket 状态与确定性 ID

<!-- journey: chapter=3 tests_added=1 -->

## English

### Goal

Introduce the Bucket aggregate, legal versioning transitions, and deterministic identities.

### Deliverable files

- `src/minis3/bucket.py`
- `tests/test_bucket.py`

### The problem at this point

Stage 01 can describe one value but cannot decide what PUT or DELETE does to an existing history. Those decisions must live together; otherwise service, storage, and listing code could each implement a different versioning rule.

### Failure preview

Once a bucket has produced named history, returning to `UNVERSIONED` makes the model claim that versioning never existed. Later code could then replace or discard that history under the wrong rules, and persistence would make the corruption durable.

### Test contract

<!-- journey-file: tests/test_bucket.py -->
#### `tests/test_bucket.py`

##### What it is and why it appears

This contract exercises the aggregate before service and disk layers can hide the source of an error.

##### Runtime role

It writes an unversioned value, enables versioning, writes again, suspends versioning, and then attempts the forbidden return to `UNVERSIONED`. The same sequence also proves deterministic `null/e00000001` and `v00000002/e00000002` identities.

##### Key code

```python
with pytest.raises(ValueError):
    bucket.set_versioning(VersioningState.UNVERSIONED)
```

##### Statement understanding

The failure is part of domain behavior, not merely validation style: once named versions can exist, “never versioned” is no longer a truthful state.

### Basic concepts

An aggregate is the owner of a related set of state transitions. Here one `Bucket` owns its versioning state and every per-key `ObjectRecord`. `UNVERSIONED` means versioning has never been enabled; `SUSPENDED` means it was enabled and new writes use the public `null` slot while named history remains.

Public `version_id` and internal `storage_id` solve different problems. A suspended bucket may reuse public ID `null`, but immutable disk artifacts still need unique internal names. A monotonic injected sequence produces both forms reproducibly.

### Why this mechanism is necessary

Scattering branches across callers would allow illegal transitions and inconsistent replacement rules. Centralizing them in Bucket makes PUT, GET, and DELETE operate on one history model. Deterministic IDs also let restart recovery resume after the largest published sequence instead of relying on random values.

### Runtime mental model

A caller supplies a command and `SequenceCounter`. Bucket validates its state, obtains one sequence, constructs a new version or marker, and replaces the exact key's immutable `ObjectRecord`. Enabled writes prepend history; unversioned and suspended writes replace only the `null` slot.

### Mechanism blocks

<!-- journey-file: src/minis3/bucket.py -->
#### `src/minis3/bucket.py`

##### What it is and why it appears

This mutable aggregate is the single owner of legal versioning changes and per-key histories. Persistence remains outside it.

##### Runtime role

Service code will call `set_versioning`, `put`, `get`, and `delete`. Each method turns one current Bucket state into the next state or raises before mutation.

##### Key code

```python
if self.versioning is VersioningState.ENABLED:
    versions = (version, *old.versions)
else:
```

##### Statement understanding

Enabled PUT preserves every earlier version by prepending. The `else` branch deliberately replaces the public `null` slot while retaining named history; treating both branches alike would break suspended semantics.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`. It proves the focused transition and identity contract, but not disk recovery or concurrent service calls.

### Durable takeaways

Bucket owns history transitions; public version identity and internal artifact identity are separate; enabled and suspended are not interchangeable.

### Explain it in your own words

The Bucket aggregate prevents every caller from inventing its own versioning behavior. It uses one deterministic sequence to order changes, keeps named history when required, and refuses transitions that would make existing history impossible to interpret.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

## 中文

### 目标

引入 Bucket 聚合、合法版本化迁移与确定性身份。

### 交付文件

- `src/minis3/bucket.py`
- `tests/test_bucket.py`

### 当前遇到的问题

Stage 01 只能描述一份值，还不能决定已有历史上的 PUT 或 DELETE 应该做什么。这些规则必须由同一个边界拥有，否则服务、存储和 Listing 可能各自实现不同的版本化语义。

### 先看会坏在哪里

Bucket 一旦产生过具名历史，再回到 `UNVERSIONED` 就等于宣称“版本化从未存在”。后续代码可能因此按错误规则替换或丢弃具名历史，引入持久化后还会把这种破坏落盘。

### 测试契约

<!-- journey-file: tests/test_bucket.py -->
#### `tests/test_bucket.py`

##### 是什么，为什么现在需要

这个契约先单测聚合，避免服务层和磁盘层掩盖错误来源。

##### 在运行时做什么

它依次写入未版本化值、启用版本化、再次写入、暂停版本化，最后尝试禁止的 `UNVERSIONED` 倒退。同一序列还证明身份可确定地产生 `null/e00000001` 与 `v00000002/e00000002`。

##### 关键代码

```python
with pytest.raises(ValueError):
    bucket.set_versioning(VersioningState.UNVERSIONED)
```

##### 关键语句理解

这个失败属于领域行为：一旦可能存在具名版本，“从未版本化”就不再是真实状态。

### 基本概念

聚合是相关状态迁移的所有者。这里一个 `Bucket` 同时拥有版本化状态与每个 Key 的 `ObjectRecord`。`UNVERSIONED` 表示从未启用；`SUSPENDED` 表示曾经启用，之后新写入使用公开 `null` 槽，但具名历史仍保留。

公开 `version_id` 与内部 `storage_id` 解决不同问题。暂停状态可以反复使用公开 ID `null`，但不可变磁盘 Artifact 仍需要唯一内部名称。注入的单调序列可复现地生成两者。

### 为什么需要这个机制

如果分支散落在调用方，非法迁移和替换规则很容易不一致。集中到 Bucket 后，PUT、GET、DELETE 共用一套历史模型。确定性 ID 还让恢复逻辑能从最大已发布序列继续，而不是依赖随机值。

### 运行时心智模型

调用方给出命令和 `SequenceCounter`。Bucket 校验状态、取一个序列、构造新版本或 Marker，再替换精确 Key 的不可变 `ObjectRecord`。Enabled 写入追加历史；未版本化和暂停写入只替换 `null` 槽。

### 机制板块

<!-- journey-file: src/minis3/bucket.py -->
#### `src/minis3/bucket.py`

##### 是什么，为什么现在需要

这个可变聚合是合法版本状态与每 Key 历史的唯一所有者，持久化仍留在外部。

##### 在运行时做什么

服务层会调用 `set_versioning`、`put`、`get`、`delete`。每个方法把当前 Bucket 状态变成下一状态，或者在变更前抛错。

##### 关键代码

```python
if self.versioning is VersioningState.ENABLED:
    versions = (version, *old.versions)
else:
```

##### 关键语句理解

Enabled PUT 通过前插保留全部旧版本；`else` 则替换公开 `null` 槽并保留具名历史。把两个分支写成一样会破坏暂停语义。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-bucket-state/tests.txt)`。它证明聚合迁移与身份契约，但还不证明磁盘恢复或并发服务调用。

### 需要真正记住的内容

Bucket 拥有历史迁移；公开版本身份与内部 Artifact 身份分离；Enabled 与 Suspended 不能混为一谈。

### 用自己的话讲清楚

Bucket 聚合阻止每个调用方自行发明版本化规则。它用确定性序列排序变更，在需要时保留具名历史，并拒绝会让现有历史无法解释的状态迁移。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)
