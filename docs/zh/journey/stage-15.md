# Stage 15 · 公开 API 与守链收官

### 目标

公开完整教学 API，并证明按 Stage 构建的源码与 Journey 测试逐字节等于 main。

??? note "交付文件"
    - `src/minis3/__init__.py`

### 当前遇到的问题

所有机制都已存在，但累积 import 仍可能意外公开内部名称，或漏掉预期名称。行为测试通过也不能单独证明 Journey 重建的是当前维护的精确源码与测试集合。

### 先看会坏在哪里

Parity 命令在全新树中重放每个 patch，再与 main 比较字节。即使窄范围 pytest 仍绿，只要漏一条 export 或 Stage 测试过期，检查就会失败。这直接捕获学习路径与完成仓库之间的漂移。

### 基本概念

公开 API 是有意选择的兼容边界，不是模块里当前能 import 的全部名称。`__all__` 记录这个选择。源码 parity 与行为证据互补：测试证明选定语义，字节比较证明重建 Artifact 就是维护中的 Artifact。

### 为什么需要这个机制

课程可能逐渐变成脱离源码的 toy，同时自己的示例仍然通过。用精确 export 与字节 parity 收官，能把源码对齐变成可执行属性，而不是 README 声明。

### 运行时心智模型

用户 import 通过 `src/minis3/__init__.py` 解析。另一边，`build_journey.py --check` 从空 Journey 根开始应用 15 个 canonical patch，收集 Journey 自有测试，再把重建字节与当前 main 比较，不移动 refs。

### 逐文件走读

#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

包根得到最终显式导出列表，覆盖值、服务、策略、结果与公开失败。

##### 在运行时做什么

它是稳定的学习者导入边界；内部存储 helper 和实现函数继续不公开。

##### 关键代码

```python
__all__ = [
```

##### 关键语句理解

这份列表把隐式 imports 集合变成有意契约；以后在内部增加 helper，也不会意外变成公开 API。

??? note "文件差异：src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 36bc1f3..86d6755 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -32,3 +32,38 @@ from .lifecycle import (
     from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
     from .store import MiniS3
     from .storage import InjectedCrash
    +
    +__all__ = [
    +    "BucketAlreadyExists",
    +    "BucketNotEmpty",
    +    "DeleteMarker",
    +    "EntityTooSmall",
    +    "ExpirationRule",
    +    "InvalidPart",
    +    "InvalidPartOrder",
    +    "ListedObject",
    +    "ListedVersion",
    +    "ListObjectsResult",
    +    "ListObjectVersionsResult",
    +    "MiniS3",
    +    "InvalidContinuationToken",
    +    "InjectedCrash",
    +    "LifecycleAction",
    +    "LifecycleActionKind",
    +    "MIN_PART_SIZE",
    +    "MiniS3Error",
    +    "NoSuchBucket",
    +    "NoSuchKey",
    +    "NoSuchUpload",
    +    "NoSuchVersion",
    +    "NotModified",
    +    "ObjectRecord",
    +    "MultipartPart",
    +    "MultipartUpload",
    +    "PreconditionFailed",
    +    "SequenceCounter",
    +    "Version",
    +    "VersioningState",
    +    "content_etag",
    +    "evaluate_expiration",
    +]
    ```

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)` 执行累计套件，再运行 `python journey/tools/build_journey.py --check` 做源码与 Journey 测试逐字节 parity。Stage 15 不新增行为用例，因为交付物就是公开面与重建证明。

### 需要真正记住的内容

Import 面、测试通过和字节 parity 各自证明不同内容；完成要求三者都与预期课程边界一致。

### 用自己的话讲清楚

最终 Stage 让学习旅程可审计：`__all__` 声明哪些概念受公开支持，累计测试证明行为，parity 重建证明整段 Stage 序列得到的就是 main 维护的源码与测试。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/09-methodology.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-14...stage-15)

完成后可运行 `git checkout stage-15` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/15-public-api-parity/stage.patch)
