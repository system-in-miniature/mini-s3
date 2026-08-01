# Stage 12 · Multipart 崩溃恢复

### 目标

证明 Multipart 发布前保留可重试 Staging，发布后完成清理。

??? note "交付文件"
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

运行 `uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`。两个用例证明完成发布两侧，累计测试继续守住普通崩溃行为。

### 需要真正记住的内容

提交前保留 Staging 供重试；提交后保留对象并清除匹配 Staging；已发布来源消除两种状态的歧义。

### 用自己的话讲清楚

Multipart 恢复沿用普通对象的 Manifest 提交点，并用 upload 来源正确清理。发布前崩溃留下可重试上传；发布后崩溃留下完整对象，匹配的私有 Staging 可以安全丢弃。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-11...stage-12)

完成后可运行 `git checkout stage-12` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/12-multipart-recovery/stage.patch)
