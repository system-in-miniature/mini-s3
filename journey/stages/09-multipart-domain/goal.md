# Stage 09 · Multipart domain and validation / Multipart 领域与校验

<!-- journey: chapter=6 tests_added=1 -->

## English

### Goal

Model multipart upload identity, staged parts, ordered completion rules, and composite ETags before storage orchestration.

### Deliverable files

- `src/minis3/errors.py`
- `src/minis3/multipart.py`
- `tests/test_multipart_domain.py`

### The problem at this point

Whole-object PUT cannot represent a client uploading large content in independently retryable parts. Completion also cannot trust a list of part numbers alone: order, ETags, existence, and minimum nonfinal size all affect the final object.

### Failure preview

The domain contract supplies staged parts and a client completion manifest. Swapping two entries must raise `InvalidPartOrder`; naming the right part with the wrong ETag must raise `InvalidPart`. Without these checks, completion can silently assemble bytes the client did not authorize.

### Basic concepts

`MultipartUpload` identifies one private staging session. `StagedPart` owns bytes and derives its receipt (`part_number`, ETag, size). The completion manifest is the client's ordered claim about which staged parts should form the object.

A multipart ETag is not the MD5 of assembled bytes. MiniS3 decodes each quoted part MD5 to binary, concatenates those digests, hashes the concatenation, then appends `-N` for the number of parts.

### Why this mechanism is necessary

Validation is a domain rule shared by any future storage adapter. Keeping it pure prevents disk layout and service locking from obscuring errors, and ensures an invalid manifest cannot begin publication.

### Runtime mental model

`validate_completion` normalizes each client entry, enforces strictly increasing part numbers, resolves each staged part, compares ETags, checks every nonfinal part size, then returns the selected parts and composite ETag. It performs no I/O and mutation.

### File-by-file walkthrough

<!-- journey-file: src/minis3/errors.py -->
#### `src/minis3/errors.py`

##### What it is and why it appears

The public failure vocabulary gains missing-upload, invalid-part, invalid-order, and too-small-part meanings.

##### Runtime role

Domain validation and later service/storage code raise the same precise types, allowing callers to distinguish retryable identity errors from invalid completion requests.

##### Key code

```python
class EntityTooSmall(MiniS3Error):
```

##### Statement understanding

Part size is not a generic `ValueError`; it is an S3-shaped completion failure with stable meaning at the public boundary.

<!-- journey-file: src/minis3/multipart.py -->
#### `src/minis3/multipart.py`

##### What it is and why it appears

This file owns multipart values and the pure completion validator.

##### Runtime role

Storage will persist these values and the service will call the validator, but neither needs to reimplement ordering, receipt, or ETag rules.

##### Key code

```python
return tuple(selected), f'"{composite}-{len(selected)}"'
```

##### Statement understanding

The return keeps validated order and its derived composite fingerprint together. The `-N` suffix records part count and distinguishes multipart ETags from normal whole-body ETags.

<!-- journey-file: tests/test_multipart_domain.py -->
#### `tests/test_multipart_domain.py`

##### What it is and why it appears

This focused contract makes completion rules visible before durable staging is added.

##### Runtime role

It supplies explicit staged parts and manifests, proving both accepted order/composite ETag and the major rejection paths.

##### Key code

```python
def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
```

##### Statement understanding

The test name captures two independent obligations: client order is semantic, and composite hashing uses binary digests rather than concatenated hexadecimal text.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`. It proves pure completion validation only; no staged bytes are durable or visible yet.

### Durable takeaways

Multipart has its own identity and receipts; the client chooses an ordered manifest; every nonfinal part obeys size rules; composite ETag is a digest of binary digests.

### Explain it in your own words

Multipart completion is not simple concatenation. MiniS3 first verifies that the client's ordered receipts exactly match durable staged parts and size rules, then derives the composite ETag. Only a validated ordered result may later be published as one object.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

在存储编排前建模 Multipart 上传身份、暂存 Part、有序完成规则与组合 ETag。

### 交付文件

- `src/minis3/errors.py`
- `src/minis3/multipart.py`
- `tests/test_multipart_domain.py`

### 当前遇到的问题

Whole-object PUT 无法表示客户端把大内容拆成可独立重试的 Part。完成操作也不能只相信 Part 编号列表：顺序、ETag、是否存在和非末 Part 最小尺寸都会改变最终对象。

### 先看会坏在哪里

领域契约提供暂存 Part 与客户端完成清单。调换两个条目必须得到 `InvalidPartOrder`；Part 正确但 ETag 错误必须得到 `InvalidPart`。没有这些检查，完成操作可能静默拼装客户端未授权的字节。

### 基本概念

`MultipartUpload` 标识一次私有暂存会话。`StagedPart` 拥有字节并派生 receipt（Part 编号、ETag、size）。完成清单是客户端对“哪些暂存 Part 按什么顺序组成对象”的声明。

Multipart ETag 不是组装后 Body 的 MD5。MiniS3 把每个带引号 Part MD5 解码成二进制，拼接摘要，再对拼接结果哈希，最后附加 Part 数量 `-N`。

### 为什么需要这个机制

验证属于任何存储适配器都要遵守的领域规则。保持纯函数能避免磁盘布局和服务锁掩盖错误，也保证无效清单不会开始发布。

### 运行时心智模型

`validate_completion` 规范化客户端条目、要求 Part 编号严格递增、解析每个暂存 Part、比较 ETag、检查所有非末 Part 尺寸，最后返回选中 Part 与组合 ETag。它不执行 I/O 和变更。

### 逐文件走读

<!-- journey-file: src/minis3/errors.py -->
#### `src/minis3/errors.py`

##### 是什么，为什么现在需要

公开失败词汇增加缺上传、无效 Part、顺序无效和 Part 太小。

##### 在运行时做什么

领域验证和后续服务/存储共享这些精确类型，使调用方能区分上传身份错误与无效完成请求。

##### 关键代码

```python
class EntityTooSmall(MiniS3Error):
```

##### 关键语句理解

Part 尺寸错误不是普通 `ValueError`，而是公开边界含义稳定的 S3 风格完成失败。

<!-- journey-file: src/minis3/multipart.py -->
#### `src/minis3/multipart.py`

##### 是什么，为什么现在需要

这里拥有 Multipart 领域值与纯完成验证器。

##### 在运行时做什么

存储层会持久化这些值，服务层会调用验证器，但两者都不用重复顺序、receipt 或 ETag 规则。

##### 关键代码

```python
return tuple(selected), f'"{composite}-{len(selected)}"'
```

##### 关键语句理解

返回值把已验证顺序和派生组合指纹绑定在一起；`-N` 记录 Part 数，也让 Multipart ETag 与普通 ETag 可区分。

<!-- journey-file: tests/test_multipart_domain.py -->
#### `tests/test_multipart_domain.py`

##### 是什么，为什么现在需要

这个聚焦契约在加入持久暂存以前就让完成规则可见。

##### 在运行时做什么

它提供显式暂存 Part 与清单，证明可接受顺序/组合 ETag 和主要拒绝路径。

##### 关键代码

```python
def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
```

##### 关键语句理解

测试名锁定两个独立义务：客户端顺序有语义，组合哈希使用二进制摘要而不是十六进制文本拼接。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`。它只证明纯完成验证；暂存字节尚未持久，也尚不可见。

### 需要真正记住的内容

Multipart 有独立身份和 receipt；客户端选择有序清单；每个非末 Part 遵守尺寸规则；组合 ETag 是二进制摘要的摘要。

### 用自己的话讲清楚

Multipart 完成不是简单拼接。MiniS3 先验证客户端有序 receipt 与持久暂存 Part、尺寸规则完全一致，再派生组合 ETag；只有验证后的有序结果才能在后续发布成一个对象。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
