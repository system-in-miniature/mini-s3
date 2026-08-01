# Stage 12 · Multipart 崩溃恢复

### 目标

证明完成崩溃的两侧：发布前保留可重试暂存，发布后清理暂存。

### 交付文件

- `tests/test_storage.py`

### 机制走读

#### 所有权与数据流

这个纯测试 Stage 用已发布对象的 `multipart_upload_id` 关联私有暂存：发布前保留暂存，发布后幂等清理。

#### 失败与排查

重启后把 Manifest 可见性与 Upload 目录存在性成对检查；在错误崩溃窗口同时缺失或同时保留都暴露恢复问题。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `tests/test_storage.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `test_multipart_complete_crash_before_publish_keeps_upload_not_object`, `test_multipart_complete_crash_after_publish_recovers_object_and_cleans_upload`

??? note "文件差异：tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    index afc9a8a..96bc973 100644
    --- a/tests/test_storage.py
    +++ b/tests/test_storage.py
    @@ -4,7 +4,13 @@ from pathlib import Path

     import pytest

    -from minis3 import InjectedCrash, MiniS3, NoSuchKey, SequenceCounter
    +from minis3 import (
    +    InjectedCrash,
    +    MiniS3,
    +    NoSuchKey,
    +    NoSuchUpload,
    +    SequenceCounter,
    +)
     from minis3.bucket import Bucket
     from minis3.storage import atomic, disk
     from minis3.storage.disk import DiskStorage
    @@ -152,3 +158,56 @@ def test_recovery_removes_spurious_tmp_files(tmp_path: Path) -> None:
         MiniS3(tmp_path)

         assert not stray.exists()
    +
    +
    +def test_multipart_complete_crash_before_publish_keeps_upload_not_object(
    +    tmp_path: Path,
    +) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    staging = MiniS3(tmp_path, minimum_part_size=3)
    +    upload = staging.create_multipart_upload("b", "movie")
    +    first = staging.upload_part("b", "movie", upload.upload_id, 1, b"abc")
    +    last = staging.upload_part("b", "movie", upload.upload_id, 2, b"x")
    +    crashing = MiniS3(
    +        tmp_path,
    +        minimum_part_size=3,
    +        crash_injector=CrashOnce("before_manifest_publish"),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.complete_multipart_upload(
    +            "b", "movie", upload.upload_id, [first, last]
    +        )
    +
    +    reopened = MiniS3(tmp_path, minimum_part_size=3)
    +    with pytest.raises(NoSuchKey):
    +        reopened.get_object("b", "movie")
    +    completed = reopened.complete_multipart_upload(
    +        "b", "movie", upload.upload_id, [first, last]
    +    )
    +    assert completed.body == b"abcx"
    +
    +
    +def test_multipart_complete_crash_after_publish_recovers_object_and_cleans_upload(
    +    tmp_path: Path,
    +) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    staging = MiniS3(tmp_path, minimum_part_size=3)
    +    upload = staging.create_multipart_upload("b", "movie")
    +    first = staging.upload_part("b", "movie", upload.upload_id, 1, b"abc")
    +    last = staging.upload_part("b", "movie", upload.upload_id, 2, b"x")
    +    crashing = MiniS3(
    +        tmp_path,
    +        minimum_part_size=3,
    +        crash_injector=CrashOnce("after_manifest_publish"),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.complete_multipart_upload(
    +            "b", "movie", upload.upload_id, [first, last]
    +        )
    +
    +    reopened = MiniS3(tmp_path, minimum_part_size=3)
    +    assert reopened.get_object("b", "movie").body == b"abcx"
    +    with pytest.raises(NoSuchUpload):
    +        reopened.abort_multipart_upload("b", "movie", upload.upload_id)
    ```

### 验证证据

`uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`

本阶段新增 2 个可执行用例，入口为 `test_multipart_complete_crash_before_publish_keeps_upload_not_object`、`test_multipart_complete_crash_after_publish_recovers_object_and_cleans_upload`。它们在机制走读之后运行，并与此前 Stage 的用例一起守住累计行为。

### 概念检查

本阶段完成后，哪条不变量必须保持成立？

??? note "答案"
    恢复逻辑用已发布对象的 upload ID 建立关联，使清理具备幂等性。

### 代码阅读检查

从 `tests/test_storage.py` 的 `test_multipart_complete_crash_before_publish_keeps_upload_not_object` 开始：进入这个边界的状态或值是什么，结果又交给哪个所有者？

??? note "答案"
    调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

### 面试表达

恢复逻辑用已发布对象的 upload ID 建立关联，使清理具备幂等性。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-11...stage-12)

完成后可运行 `git checkout stage-12` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/12-multipart-recovery/stage.patch)
