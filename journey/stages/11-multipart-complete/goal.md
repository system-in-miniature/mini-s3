# Stage 11 · Atomic multipart completion / Multipart 原子完成

<!-- journey: chapter=6 tests_added=4 -->

## English

### Goal

Validate an ordered completion manifest, assemble staged bytes, and publish exactly one visible object.

### Deliverable files

- `src/minis3/store.py`
- `tests/test_multipart.py`

### The problem at this point

Parts are durable but intentionally invisible. Completion must turn selected private parts into one normal version without exposing intermediate bytes, accepting stale receipts, or deleting retryable staging before publication succeeds.

### Test contract

#### See the failure first

The main contract uploads two parts and confirms List is empty before completion. After completion it requires body `abcend`, a two-part composite ETag different from the whole-body ETag, and exactly one visible key. Any early ObjectRecord or wrong ETag is immediately visible.

<!-- journey-file: tests/test_multipart.py -->
#### `tests/test_multipart.py`

##### What it is and why it appears

Four cases cover invisibility until completion, same-number replacement, manifest validation, abort, and restart of unfinished staging.

##### Runtime role

They exercise the complete public lifecycle and inspect both visible objects and private upload behavior.

##### Key code

```python
assert completed.etag != content_etag(completed.body)
```

##### Statement understanding

This prevents an easy but incorrect implementation from hashing assembled bytes as a normal PUT. Multipart identity is derived from part digests.

### Basic concepts

Completion is one ordered transaction at the service boundary: reload staging, validate the client's receipt list, concatenate selected bytes, reuse Bucket PUT with the composite ETag, publish the candidate Bucket, then remove staging.

Part replacement and completion are separate. Re-uploading part 1 changes the current receipt; a client that completes with the old ETag must fail rather than assemble unexpected bytes.

### Why this mechanism is necessary

Publishing each part would violate whole-object visibility. Removing staging before the manifest commits destroys retryability. Reusing the established Bucket and manifest path keeps multipart from creating a weaker second consistency model.

### Runtime mental model

`complete_multipart_upload` holds the service lock, loads upload plus parts, calls pure `validate_completion`, joins bodies, mutates a candidate Bucket with composite ETag/provenance, persists it, swaps it into memory, and only then removes the upload directory.

### Mechanism blocks

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

The service gains the completion orchestration that connects private staging to the existing object publication path.

##### Runtime role

It owns the ordering across storage load, pure validation, Bucket mutation, manifest publication, and staging cleanup.

##### Key code

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
self._storage.remove_multipart_upload(bucket, key, upload_id)
```

##### Statement understanding

Cleanup is last. If publication fails, the upload remains retryable; once publication succeeds, removing staging cannot make the committed object disappear.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`. The cases prove normal completion and validation. Crash recovery on either side of publication is isolated in Stage 12.

### Durable takeaways

Completion validates before mutation, publishes one candidate object, and cleans staging only after commit. Multipart ETag remains distinct from whole-body ETag.

### Explain it in your own words

MiniS3 treats completion as the bridge from private staged parts to one ordinary visible version. It validates the client's exact ordered receipts, assembles bytes, uses the established manifest publication boundary, and retains staging whenever publication has not committed.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

校验有序完成清单、组装暂存字节，并只发布一个可见对象。

### 交付文件

- `src/minis3/store.py`
- `tests/test_multipart.py`

### 当前遇到的问题

Part 已经持久但刻意不可见。完成操作必须把选中的私有 Part 变成一个普通版本，同时不能暴露中间字节、接受过期 receipt，或者在发布成功前删除可重试 Staging。

### 测试契约

#### 先看会坏在哪里

主契约上传两个 Part，并在完成前确认 List 为空。完成后要求 Body 为 `abcend`、ETag 是不同于 whole-body ETag 的两 Part 组合 ETag，并且只出现一个可见 Key。提前创建 ObjectRecord 或算错 ETag 都会直接暴露。

<!-- journey-file: tests/test_multipart.py -->
#### `tests/test_multipart.py`

##### 是什么，为什么现在需要

四个场景覆盖完成前不可见、同编号替换、清单验证、Abort 和未完成上传重启。

##### 在运行时做什么

它们运行完整公开生命周期，同时观察可见对象与私有上传行为。

##### 关键代码

```python
assert completed.etag != content_etag(completed.body)
```

##### 关键语句理解

这防止实现偷懒地把组装 Body 当普通 PUT 计算哈希；Multipart 身份来自 Part 摘要。

### 基本概念

完成是服务边界的一次有序事务：重载 Staging、校验客户端 receipt 列表、拼接选中字节、用组合 ETag 复用 Bucket PUT、发布候选 Bucket，最后删除 Staging。

Part 替换与完成分开。重传 Part 1 会改变当前 receipt；客户端用旧 ETag 完成时必须失败，不能拼装它没有确认的新字节。

### 为什么需要这个机制

逐 Part 发布会破坏 whole-object 可见性；Manifest 提交前删除 Staging 会摧毁重试能力。复用已有 Bucket 与 Manifest 路径，避免 Multipart 建立一套更弱的第二一致性模型。

### 运行时心智模型

`complete_multipart_upload` 持有服务锁，加载 upload 与 parts，调用纯 `validate_completion`，拼接 Body，用组合 ETag/来源修改候选 Bucket，持久化并替换内存，最后才删除上传目录。

### 机制板块

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

服务增加完成编排，把私有 Staging 接到已有对象发布路径。

##### 在运行时做什么

它拥有存储加载、纯验证、Bucket 变更、Manifest 发布与 Staging 清理之间的顺序。

##### 关键代码

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
self._storage.remove_multipart_upload(bucket, key, upload_id)
```

##### 关键语句理解

清理必须最后执行。发布失败时上传仍可重试；发布成功后再删 Staging，也不会让已提交对象消失。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`。这些用例证明正常完成与验证；发布两侧的崩溃恢复由 Stage 12 单独锁定。

### 需要真正记住的内容

完成在变更前验证，只发布一个候选对象，并在提交后才清理 Staging；Multipart ETag 与 whole-body ETag 保持不同。

### 用自己的话讲清楚

MiniS3 把完成操作作为私有暂存 Part 到一个普通可见版本的桥梁。它校验客户端精确有序 receipt，组装字节，复用 Manifest 发布边界，并在尚未提交时保留 Staging 供重试。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
