# Stage 04 · Object service facade / 对象服务门面

<!-- journey: chapter=2 tests_added=15 -->

## English

### Goal

Join Bucket and DiskStorage behind one locked public service for bucket and object operations.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/store.py`
- `tests/test_storage.py`
- `tests/test_versioning.py`

### The problem at this point

The domain can calculate a next Bucket and storage can publish it, but callers still have to coordinate both. Without a service owner, one code path could mutate memory without persistence while another could race halfway through a transition.

### Failure preview

The restart contract writes two versions, opens a fresh `MiniS3`, reads both bodies, then writes again and requires a new ID. It exposes two distinct bugs at once: state not published to disk, or the recovered sequence counter reusing an old identity.

### Basic concepts

An application service coordinates existing owners; it does not absorb their responsibilities. Bucket still decides legal history, DiskStorage still decides publication and recovery, and `MiniS3` owns the public operation, lock, lookup, and ordering between them.

The implementation mutates a deep-copied candidate, persists it, and only then swaps the in-memory Bucket reference. Thus a publication failure leaves the previously visible in-memory state intact.

### Why this mechanism is necessary

Locking only Bucket or only disk is insufficient because a public mutation spans both. One service lock serializes the read-check-mutate-publish sequence, while candidate publication avoids exposing uncommitted memory.

### Runtime mental model

`put_object` acquires the lock, resolves a Bucket, copies it, delegates PUT to the candidate, persists the candidate, swaps it into `_buckets`, and returns the Version. GET and HEAD read under the same lock; HEAD reuses GET because this protocol-free model returns the same metadata value.

### File-by-file walkthrough

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

This is the public application boundary that coordinates locking, aggregate transitions, persistence, and recovery.

##### Runtime role

Every public bucket/object call enters here. Successful mutations cross Bucket then DiskStorage; reads resolve the current in-memory aggregate.

##### Key code

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
```

##### Statement understanding

Publication occurs before the candidate becomes the process-visible Bucket. Reversing these lines would let a failed disk write leak state that disappears after restart.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

The package now exports `MiniS3` and versioning state in addition to the value model.

##### Runtime role

It establishes the intended entry point; callers no longer need to assemble Bucket and DiskStorage themselves.

##### Statement understanding

Public export is API wiring, not proof of runtime behavior. The service tests below provide that evidence.

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### What it is and why it appears

These contracts exercise persistence through the public service, including restart, crash injection, bucket deletion, and sequence recovery.

##### Runtime role

They detect gaps between in-memory success and reopened state. This is where orchestration and storage meet.

##### Key code

```python
assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
```

##### Statement understanding

Addressing the old version after constructing `reopened` proves both the version history and its bytes survived publication; checking only the latest value would be weaker.

<!-- journey-file: tests/test_versioning.py -->
#### `tests/test_versioning.py`

##### What it is and why it appears

This file locks the full public versioning state machine and DELETE meanings.

##### Runtime role

It distinguishes unversioned deletion, marker creation, specific-version deletion, latest-marker 404 behavior, and retained named history.

##### Key code

```python
assert bucket.get("k", historical.version_id) == historical
```

##### Statement understanding

The defensive case proves an unversioned delete cannot erase a named version already present in recovered or externally constructed history.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/04-object-service/tests.txt)`. Fifteen cases cover service orchestration and version behavior. They do not yet prove listing projections or injected crash outcomes around the manifest rename.

### Durable takeaways

The service owns orchestration and locking; Bucket owns domain transitions; storage owns durability; persist-before-swap keeps memory aligned with committed state.

### Explain it in your own words

`MiniS3` turns separate domain and storage components into one consistent public operation. It serializes the whole transition, publishes a candidate Bucket before exposing it, and therefore keeps current memory and restart-visible state on the same side of a failed write.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/02-objects-etag.md)

## 中文

### 目标

在一个带锁公开服务后连接 Bucket 与 DiskStorage，提供 Bucket 和对象操作。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/store.py`
- `tests/test_storage.py`
- `tests/test_versioning.py`

### 当前遇到的问题

领域层能计算下一份 Bucket，存储层也能发布它，但调用方仍需自己协调两者。缺少服务所有者时，一条路径可能只改内存不持久化，另一条路径可能在状态迁移中途与它竞争。

### 先看会坏在哪里

重启契约写入两个版本，再打开全新的 `MiniS3` 读取两份 Body，随后继续写入并要求新 ID。它同时暴露两类错误：状态没有真正发布到磁盘，或者恢复后的序列计数器复用了旧身份。

### 基本概念

应用服务负责协调已有所有者，而不是吞掉它们的职责。Bucket 仍决定合法历史，DiskStorage 仍决定发布和恢复，`MiniS3` 拥有公开操作、锁、查找以及两者之间的调用顺序。

实现先深拷贝候选 Bucket，对候选执行变更并持久化，最后才替换内存引用。因此发布失败时，原本可见的内存状态不会被污染。

### 为什么需要这个机制

只锁 Bucket 或只锁磁盘都不够，因为公开变更跨越两者。服务锁串行化“读取—检查—变更—发布”，候选发布则避免暴露未提交内存。

### 运行时心智模型

`put_object` 加锁、解析 Bucket、复制候选、把 PUT 委托给候选、持久化候选、替换 `_buckets`，最后返回 Version。GET/HEAD 在同一把锁下读取；HEAD 复用 GET，因为当前协议无关模型返回相同元数据值。

### 逐文件走读

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

这是公开应用边界，协调锁、聚合迁移、持久化与恢复。

##### 在运行时做什么

所有公开 Bucket/对象调用从这里进入。成功变更依次跨过 Bucket 和 DiskStorage；读取解析当前内存聚合。

##### 关键代码

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
```

##### 关键语句理解

候选先发布，之后才成为进程可见 Bucket。反过来会让失败的磁盘写入泄漏成“当前可见但重启消失”的状态。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

包现在除领域值外，还导出 `MiniS3` 与版本化状态。

##### 在运行时做什么

它建立预期入口，调用方不再需要自行拼装 Bucket 与 DiskStorage。

##### 关键语句理解

公开导出只是 API 接线，不证明运行时行为；下面的服务测试才提供证据。

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### 是什么，为什么现在需要

这些契约通过公开服务检查持久化，包括重启、崩溃注入、Bucket 删除和序列恢复。

##### 在运行时做什么

它们捕获“内存成功但重开失败”的缺口，是编排层与存储层相遇的位置。

##### 关键代码

```python
assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
```

##### 关键语句理解

在新实例上按旧版本 ID 读取，证明版本历史和字节都跨发布保存；只检查最新值证据更弱。

<!-- journey-file: tests/test_versioning.py -->
#### `tests/test_versioning.py`

##### 是什么，为什么现在需要

这里锁定完整公开版本状态机和 DELETE 含义。

##### 在运行时做什么

它区分未版本化删除、Marker 创建、指定版本删除、最新 Marker 导致 404，以及具名历史保留。

##### 关键代码

```python
assert bucket.get("k", historical.version_id) == historical
```

##### 关键语句理解

这个防御性场景证明：即使恢复或外部构造中出现具名历史，未版本化删除也不能把它擦掉。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/04-object-service/tests.txt)`。15 个用例覆盖服务编排与版本行为，但还不证明 Listing 投影或 Manifest rename 两侧的注入崩溃结果。

### 需要真正记住的内容

服务拥有编排和锁，Bucket 拥有领域迁移，存储拥有持久化；先 persist 再 swap 让内存与已提交状态一致。

### 用自己的话讲清楚

`MiniS3` 把领域组件和存储组件组成一次一致的公开操作。它串行化完整迁移，在暴露候选 Bucket 前先发布，所以写入失败时当前内存与重启可见状态会留在同一侧。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/02-objects-etag.md)
