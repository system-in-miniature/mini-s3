# Stage 09 · Multipart 领域与校验

### 目标

建模上传身份、暂存 Part、完成清单、尺寸规则与组合 ETag。

### 交付文件

- `src/minis3/errors.py`
- `src/minis3/multipart.py`

### 机制走读

#### 所有权与数据流

`multipart.py` 拥有 Upload/Part 值和纯完成校验：客户端清单选择暂存 Part，校验顺序与尺寸，再生成组合 ETag。

#### 失败与排查

组装前对照客户端身份与暂存回执；乱序、缺失 Part、ETag 不匹配和非末尾 Part 过小必须分别失败。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/errors.py`

共享的领域失败词汇。

由 Bucket/服务代码构造并向上返回，不拥有 I/O；状态正确但结果异常时检查这些字段。

**变化锚点:** `NoSuchUpload`, `InvalidPart`, `InvalidPartOrder`, `EntityTooSmall`

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

#### `src/minis3/multipart.py`

Multipart 领域值与完成规则。

由 `MiniS3` 作为策略函数调用；接收显式值并返回由服务执行的决策。

**变化锚点:** `MultipartUpload`, `MultipartPart`, `StagedPart`, `etag`, `size`, `receipt`, `_entry_identity`, `validate_completion`

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

#### `tests/test_multipart_domain.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `test_completion_validation_orders_parts_and_hashes_binary_digests`

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

### 验证证据

`uv run pytest -q $(cat journey/stages/09-multipart-domain/tests.txt)`

本阶段新增 1 个可执行用例，入口为 `test_completion_validation_orders_parts_and_hashes_binary_digests`。它们在机制走读之后运行，并与此前 Stage 的用例一起守住累计行为。

### 概念检查

本阶段完成后，哪条不变量必须保持成立？

??? note "答案"
    只有完成时才能知道最后一个 Part，因此最小尺寸也在完成时校验。

### 代码阅读检查

从 `src/minis3/multipart.py` 的 `MultipartUpload` 开始：进入这个边界的状态或值是什么，结果又交给哪个所有者？

??? note "答案"
    由 `MiniS3` 作为策略函数调用；接收显式值并返回由服务执行的决策。

### 面试表达

只有完成时才能知道最后一个 Part，因此最小尺寸也在完成时校验。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-08...stage-09)

完成后可运行 `git checkout stage-09` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/09-multipart-domain/stage.patch)
