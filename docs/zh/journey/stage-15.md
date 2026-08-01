# Stage 15 · 公开 API 与守链收官

### 目标

公开完整教学 API，并证明重建后的源码与 Journey 所有的测试逐字节等于 main。

### 动手任务

从stage-14开始，完成 `minis3.__init__` 导出，并运行完整 49 项测试契约。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `src/minis3/__init__.py`

### 机制走读

#### 所有权与数据流

`minis3.__init__` 是受支持的适配器接口；Journey Builder 随后应用全部 Patch，并把最终 `src/minis3` 与 Journey 所有的测试和 main 逐字节比较。仅服务网站的文档测试不属于重建契约。

#### 失败与排查

导入失败属于导出接线问题；最终 Parity 失败会列出缺失、多余或变化文件，必须修复 Stage 链，不能藏在生成 Commit 中。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/__init__.py`

受支持的包级公开接口。

由用户导入触达；接线错误会在运行时流程开始前表现为名称缺失。

**变化锚点:** 配置、导出或文档变化

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

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        只有 CI 同时守护行为与最终源码一致性，重建旅程才可信。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)`

### 对应真实 S3 的一课

只有 CI 同时守护行为与最终源码一致性，重建旅程才可信。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/09-methodology.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-14...stage-15)

完成后可运行 `git checkout stage-15` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/15-public-api-parity/stage.patch)
