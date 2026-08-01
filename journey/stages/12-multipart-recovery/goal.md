# Stage 12 · Multipart crash recovery / Multipart 崩溃恢复

<!-- journey: chapter=6 tests_added=2 -->

## English

### Goal

Prove retryable staging before multipart publication and cleanup after publication.

### Deliverable files

- `tests/test_storage.py`

### The problem at this point

Normal completion order is correct, but a crash can interrupt after assembly at either side of manifest publication. Recovery must not guess from the presence of staged files; it must correlate published object provenance with upload identity.

### Failure preview

The pre-publication test crashes completion at `before_manifest_publish`, reopens, and completes the same upload successfully. If recovery deletes all staging eagerly, the retry becomes impossible even though no object was committed.

### Basic concepts

Before publication, staging is the only durable owner of the requested completion and must remain. After publication, the object version's `multipart_upload_id` proves that this upload committed, so leftover staging is redundant debris and may be removed.

### Why this mechanism is necessary

Using directory existence alone cannot distinguish an unfinished upload from post-commit cleanup interrupted by a crash. Correlating published provenance with upload ID makes both cases deterministic.

### Runtime mental model

Each test prepares a durable upload and parts, injects one crash point, discards the crashing service, and reopens. The before case retries completion; the after case reads the object and verifies abort now reports `NoSuchUpload` because recovery cleaned staging.

### File-by-file walkthrough

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### What it is and why it appears

The storage recovery suite gains the two-sided multipart completion crash contract.

##### Runtime role

It uses fresh service instances to make published manifest and recovered staging—not stale memory—the only evidence.

##### Key code

```python
assert reopened.get_object("b", "movie").body == b"abcx"
```

##### Statement understanding

In the after-publish case, the visible complete object is authoritative even if cleanup did not run. Recovery must keep it and remove only the matching upload staging.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`. Two tests prove both sides of completion publication and the cumulative suite guards ordinary crash behavior.

### Durable takeaways

Before commit, keep staging for retry. After commit, keep the object and remove matching staging. Published provenance disambiguates the two states.

### Explain it in your own words

Multipart recovery follows the same manifest commit point as normal objects, but uses upload provenance to clean correctly. A crash before publication leaves a retryable upload; a crash after publication leaves a complete object whose matching private staging is safe to discard.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

证明 Multipart 发布前保留可重试 Staging，发布后完成清理。

### 交付文件

- `tests/test_storage.py`

### 当前遇到的问题

正常完成顺序正确，但崩溃可能发生在组装后、Manifest 发布的任一侧。恢复不能根据暂存文件是否存在来猜测，必须把已发布对象来源与 upload 身份关联起来。

### 先看会坏在哪里

发布前测试在 `before_manifest_publish` 崩溃，重开后使用同一个 upload 成功完成。如果恢复一律删除 Staging，即使对象从未提交也无法重试。

### 基本概念

发布前，Staging 是完成请求唯一持久所有者，必须保留。发布后，对象版本的 `multipart_upload_id` 证明该 upload 已提交，残留 Staging 就是可删除冗余。

### 为什么需要这个机制

只看目录存在无法区分“未完成上传”和“提交后清理被崩溃打断”。用已发布来源关联 upload ID，两个场景都有确定答案。

### 运行时心智模型

每条测试准备持久 upload 与 parts，注入一个崩溃点，丢弃崩溃服务再重开。Before 场景重试完成；After 场景读取对象，并确认 Abort 得到 `NoSuchUpload`，因为恢复已清理 Staging。

### 逐文件走读

<!-- journey-file: tests/test_storage.py -->
#### `tests/test_storage.py`

##### 是什么，为什么现在需要

存储恢复套件增加 Multipart 完成的双侧崩溃契约。

##### 在运行时做什么

它使用全新服务实例，让已发布 Manifest 与恢复后的 Staging 成为唯一证据，而不是旧内存。

##### 关键代码

```python
assert reopened.get_object("b", "movie").body == b"abcx"
```

##### 关键语句理解

在发布后场景，即使清理尚未运行，可见完整对象仍是权威。恢复必须保留它，只删除匹配的 upload Staging。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`。两个用例证明完成发布两侧，累计测试继续守住普通崩溃行为。

### 需要真正记住的内容

提交前保留 Staging 供重试；提交后保留对象并清除匹配 Staging；已发布来源消除两种状态的歧义。

### 用自己的话讲清楚

Multipart 恢复沿用普通对象的 Manifest 提交点，并用 upload 来源正确清理。发布前崩溃留下可重试上传；发布后崩溃留下完整对象，匹配的私有 Staging 可以安全丢弃。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
