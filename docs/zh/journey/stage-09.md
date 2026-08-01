# Stage 09 · Multipart 领域与校验

### 目标

在存储编排前建模 Multipart 上传身份、暂存 Part、有序完成规则与组合 ETag。

??? note "交付文件"
    - `src/minis3/errors.py`
    - `src/minis3/multipart.py`
    - `tests/test_multipart_domain.py`

### 当前遇到的问题

Whole-object PUT 无法表示客户端把大内容拆成可独立重试的 Part。完成操作也不能只相信 Part 编号列表：顺序、ETag、是否存在和非末 Part 最小尺寸都会改变最终对象。

### 先看会坏在哪里

领域契约提供暂存 Part 与客户端完成清单。调换两个条目必须得到 `InvalidPartOrder`；Part 正确但 ETag 错误必须得到 `InvalidPart`。没有这些检查，完成操作可能静默拼装客户端未授权的字节。

### 测试契约

??? note "文件差异：tests/test_multipart_domain.py"
    ```diff
    diff --git a/tests/test_multipart_domain.py b/tests/test_multipart_domain.py
    new file mode 100644
    index 0000000..9b7026a
    --- /dev/null
    +++ b/tests/test_multipart_domain.py
    @@ -0,0 +1,40 @@
    +"""Focused contract for multipart validation before storage orchestration."""
    +
    +from hashlib import md5
    +
    +import pytest
    +
    +from minis3.errors import EntityTooSmall, InvalidPartOrder
    +from minis3.multipart import StagedPart, validate_completion
    +
    +
    +def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
    +    first = StagedPart(1, b"abc")
    +    last = StagedPart(2, b"x")
    +    staged = {1: first, 2: last}
    +
    +    selected, etag = validate_completion(
    +        staged,
    +        [first.receipt, last.receipt],
    +        minimum_part_size=3,
    +    )
    +
    +    binary_digests = b"".join(
    +        md5(part.body, usedforsecurity=False).digest() for part in selected
    +    )
    +    expected = md5(binary_digests, usedforsecurity=False).hexdigest()
    +    assert selected == (first, last)
    +    assert etag == f'"{expected}-2"'
    +
    +    with pytest.raises(InvalidPartOrder):
    +        validate_completion(
    +            staged,
    +            [last.receipt, first.receipt],
    +            minimum_part_size=3,
    +        )
    +    with pytest.raises(EntityTooSmall):
    +        validate_completion(
    +            {1: StagedPart(1, b"a"), 2: last},
    +            [StagedPart(1, b"a").receipt, last.receipt],
    +            minimum_part_size=3,
    +        )
    ```

**测试锁定什么**

这个聚焦契约在加入持久暂存以前就让完成规则可见。

**如何构造反例**

它提供显式暂存 Part 与清单，证明可接受顺序/组合 ETag 和主要拒绝路径。

**关键测试语句**

```python
def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
```

**失败意味着什么**

测试名锁定两个独立义务：客户端顺序有语义，组合哈希使用二进制摘要而不是十六进制文本拼接。

### 基本概念

`MultipartUpload` 标识一次私有暂存会话。`StagedPart` 拥有字节并派生 receipt（Part 编号、ETag、size）。完成清单是客户端对“哪些暂存 Part 按什么顺序组成对象”的声明。

Multipart ETag 不是组装后 Body 的 MD5。MiniS3 把每个带引号 Part MD5 解码成二进制，拼接摘要，再对拼接结果哈希，最后附加 Part 数量 `-N`。

### 为什么需要这个机制

验证属于任何存储适配器都要遵守的领域规则。保持纯函数能避免磁盘布局和服务锁掩盖错误，也保证无效清单不会开始发布。

### 运行时心智模型

`validate_completion` 规范化客户端条目、要求 Part 编号严格递增、解析每个暂存 Part、比较 ETag、检查所有非末 Part 尺寸，最后返回选中 Part 与组合 ETag。它不执行 I/O 和变更。

### 机制板块

#### Multipart 完成规则

把上传身份、有序 Part 回执、校验失败和组合 ETag 计算定义成纯领域契约。

??? note "文件差异：src/minis3/errors.py"
    ```diff
    diff --git a/src/minis3/errors.py b/src/minis3/errors.py
    index e1a2230..9db3b4c 100644
    --- a/src/minis3/errors.py
    +++ b/src/minis3/errors.py
    @@ -28,3 +28,18 @@ class NoSuchVersion(MiniS3Error):
     class InvalidContinuationToken(MiniS3Error):
         """The list continuation token was malformed or belongs to another query."""

    +
    +class NoSuchUpload(MiniS3Error):
    +    """The addressed multipart upload does not exist or no longer exists."""
    +
    +
    +class InvalidPart(MiniS3Error):
    +    """A completion entry names a missing part or the wrong part ETag."""
    +
    +
    +class InvalidPartOrder(MiniS3Error):
    +    """Multipart completion entries were not in strictly ascending order."""
    +
    +
    +class EntityTooSmall(MiniS3Error):
    +    """A non-final multipart part is below the configured minimum size."""
    ```

**是什么，为什么现在需要**

公开失败词汇增加缺上传、无效 Part、顺序无效和 Part 太小。

**在运行时做什么**

领域验证和后续服务/存储共享这些精确类型，使调用方能区分上传身份错误与无效完成请求。

**关键代码**

```python
class EntityTooSmall(MiniS3Error):
```

**关键语句理解**

Part 尺寸错误不是普通 `ValueError`，而是公开边界含义稳定的 S3 风格完成失败。

??? note "文件差异：src/minis3/multipart.py"
    ```diff
    diff --git a/src/minis3/multipart.py b/src/minis3/multipart.py
    new file mode 100644
    index 0000000..c10ab02
    --- /dev/null
    +++ b/src/minis3/multipart.py
    @@ -0,0 +1,107 @@
    +"""Multipart values and completion validation.
    +
    +An upload part cannot know whether it will be the final part in the eventual
    +completion list. Therefore the S3 minimum-size rule is intentionally checked
    +at completion, against every listed part except the last one.
    +"""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Sequence
    +from dataclasses import dataclass
    +from hashlib import md5
    +
    +from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder
    +from .model import content_etag
    +
    +
    +MIN_PART_SIZE = 5 * 1024 * 1024
    +MAX_PART_NUMBER = 10_000
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class MultipartUpload:
    +    """Identity of one durable but object-invisible upload."""
    +
    +    bucket: str
    +    key: str
    +    upload_id: str
    +    sequence: int
    +    initiated_at: float
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class MultipartPart:
    +    """Public receipt returned after one part has been durably staged."""
    +
    +    part_number: int
    +    etag: str
    +    size: int
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class StagedPart:
    +    """Bytes recovered from an upload's private staging directory."""
    +
    +    part_number: int
    +    body: bytes
    +
    +    @property
    +    def etag(self) -> str:
    +        return content_etag(self.body)
    +
    +    @property
    +    def size(self) -> int:
    +        return len(self.body)
    +
    +    @property
    +    def receipt(self) -> MultipartPart:
    +        return MultipartPart(self.part_number, self.etag, self.size)
    +
    +
    +CompletionEntry = MultipartPart | tuple[int, str]
    +
    +
    +def _entry_identity(entry: CompletionEntry) -> tuple[int, str]:
    +    if isinstance(entry, MultipartPart):
    +        return entry.part_number, entry.etag
    +    try:
    +        part_number, etag = entry
    +    except (TypeError, ValueError) as exc:
    +        raise InvalidPart(entry) from exc
    +    if not isinstance(part_number, int) or not isinstance(etag, str):
    +        raise InvalidPart(entry)
    +    return part_number, etag
    +
    +
    +def validate_completion(
    +    staged: dict[int, StagedPart],
    +    entries: Sequence[CompletionEntry],
    +    *,
    +    minimum_part_size: int,
    +) -> tuple[tuple[StagedPart, ...], str]:
    +    """Validate a client manifest and return ordered parts plus composite ETag."""
    +
    +    identities = tuple(_entry_identity(entry) for entry in entries)
    +    if not identities:
    +        raise InvalidPart("completion list must contain at least one part")
    +    numbers = tuple(part_number for part_number, _etag in identities)
    +    if any(left >= right for left, right in zip(numbers, numbers[1:])):
    +        raise InvalidPartOrder(numbers)
    +
    +    selected: list[StagedPart] = []
    +    for part_number, expected_etag in identities:
    +        part = staged.get(part_number)
    +        if part is None or part.etag != expected_etag:
    +            raise InvalidPart(f"part {part_number}")
    +        selected.append(part)
    +    for part in selected[:-1]:
    +        if part.size < minimum_part_size:
    +            raise EntityTooSmall(f"part {part.part_number}")
    +
    +    # Multipart ETags hash binary MD5 digests, not their hexadecimal strings.
    +    digests = b"".join(
    +        md5(part.body, usedforsecurity=False).digest() for part in selected
    +    )
    +    composite = md5(digests, usedforsecurity=False).hexdigest()
    +    return tuple(selected), f'"{composite}-{len(selected)}"'
    ```

**是什么，为什么现在需要**

这里拥有 Multipart 领域值与纯完成验证器。

**在运行时做什么**

存储层会持久化这些值，服务层会调用验证器，但两者都不用重复顺序、receipt 或 ETag 规则。

**关键代码**

```python
return tuple(selected), f'"{composite}-{len(selected)}"'
```

**关键语句理解**

返回值把已验证顺序和派生组合指纹绑定在一起；`-N` 记录 Part 数，也让 Multipart ETag 与普通 ETag 可区分。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`。它只证明纯完成验证；暂存字节尚未持久，也尚不可见。

### 需要真正记住的内容

Multipart 有独立身份和 receipt；客户端选择有序清单；每个非末 Part 遵守尺寸规则；组合 ETag 是二进制摘要的摘要。

### 用自己的话讲清楚

Multipart 完成不是简单拼接。MiniS3 先验证客户端有序 receipt 与持久暂存 Part、尺寸规则完全一致，再派生组合 ETag；只有验证后的有序结果才能在后续发布成一个对象。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-08...stage-09)

完成后可运行 `git checkout stage-09` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/09-multipart-domain/stage.patch)
