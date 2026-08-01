# Stage 08 · 目录 fsync 与启动清理

### 目标

验证父目录持久性，并在启动时清理临时或未引用的崩溃残留。

### 交付文件

- `tests/test_storage.py`

### 机制走读

#### 所有权与数据流

这个证明型 Stage 记录目录 fsync 边界并制造中断写入残留，再检查启动清理保留被引用 Artifact、删除临时名称。

#### 失败与排查

把每个新建或 rename 的目录项与父目录 fsync 对齐；恢复删除前，先把候选文件与 Manifest 引用逐一比较。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `tests/test_storage.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `test_atomic_write_fsyncs_each_new_directory_parent`, `recording_fsync_directory`, `test_storage_and_bucket_directory_creation_fsync_parent_chains`, `test_recovery_removes_spurious_tmp_files`

??? note "文件差异：tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    index 5faad97..afc9a8a 100644
    --- a/tests/test_storage.py
    +++ b/tests/test_storage.py
    @@ -1,7 +1,9 @@
     """Disk tests pin the manifest publication crash boundary."""

     from pathlib import Path
    +
     import pytest
    +
     from minis3 import InjectedCrash, MiniS3, NoSuchKey, SequenceCounter
     from minis3.bucket import Bucket
     from minis3.storage import atomic, disk
    @@ -96,3 +98,57 @@ def test_crash_after_manifest_publish_exposes_complete_new_state(
         visible = reopened.get_object("b", "new")
         assert visible.body == b"value"
         assert visible.etag == '"2063c1608d6e0baf80249c42e2be5804"'
    +
    +
    +def test_atomic_write_fsyncs_each_new_directory_parent(
    +    tmp_path: Path,
    +    monkeypatch: pytest.MonkeyPatch,
    +) -> None:
    +    calls: list[Path] = []
    +    real_fsync_directory = atomic.fsync_directory
    +
    +    def recording_fsync_directory(path: Path) -> None:
    +        calls.append(path)
    +        real_fsync_directory(path)
    +
    +    monkeypatch.setattr(atomic, "fsync_directory", recording_fsync_directory)
    +
    +    atomic.atomic_write(tmp_path / "one" / "two" / "value", b"payload")
    +
    +    assert calls == [tmp_path, tmp_path / "one", tmp_path / "one" / "two"]
    +
    +
    +def test_storage_and_bucket_directory_creation_fsync_parent_chains(
    +    tmp_path: Path,
    +    monkeypatch: pytest.MonkeyPatch,
    +) -> None:
    +    calls: list[Path] = []
    +    real_fsync_directory = disk.fsync_directory
    +
    +    def recording_fsync_directory(path: Path) -> None:
    +        calls.append(path)
    +        real_fsync_directory(path)
    +
    +    monkeypatch.setattr(disk, "fsync_directory", recording_fsync_directory)
    +    monkeypatch.setattr(atomic, "fsync_directory", recording_fsync_directory)
    +    root = tmp_path / "new-root"
    +    storage = DiskStorage(root)
    +    storage.create_bucket(Bucket("b"))
    +
    +    bucket_directory = storage._bucket_directory("b")
    +    temporary = storage.buckets_root / f".tmp-{bucket_directory.name}"
    +    assert tmp_path in calls
    +    assert calls.count(root) >= 1
    +    assert calls.count(storage.buckets_root) >= 2
    +    assert calls.count(temporary) >= 2
    +
    +
    +def test_recovery_removes_spurious_tmp_files(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    stray = next((tmp_path / "buckets").iterdir()) / "manifest.json.tmp-stray"
    +    stray.write_text("partial")
    +
    +    MiniS3(tmp_path)
    +
    +    assert not stray.exists()
    ```

### 验证证据

`uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`

本阶段新增 3 个可执行用例，入口为 `test_atomic_write_fsyncs_each_new_directory_parent`、`test_storage_and_bucket_directory_creation_fsync_parent_chains`、`test_recovery_removes_spurious_tmp_files`。它们在机制走读之后运行，并与此前 Stage 的用例一起守住累计行为。

### 概念检查

本阶段完成后，哪条不变量必须保持成立？

??? note "答案"
    只有对所在目录执行 fsync，原子 rename 才成为持久发布。

### 代码阅读检查

从 `tests/test_storage.py` 的 `test_atomic_write_fsyncs_each_new_directory_parent` 开始：进入这个边界的状态或值是什么，结果又交给哪个所有者？

??? note "答案"
    调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

### 面试表达

只有对所在目录执行 fsync，原子 rename 才成为持久发布。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-07...stage-08)

完成后可运行 `git checkout stage-08` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/08-fsync-recovery/stage.patch)
