# Stage 08 · 目录 fsync 与启动清理

### 目标

验证目录项持久性，以及启动时对临时和未引用崩溃残留的清理。

### 交付文件

??? note "展开交付文件"
    - `tests/test_storage.py`

### 当前遇到的问题

崩溃矩阵证明了哪个 Manifest 可见，但持久性还依赖目录项。创建嵌套目录或 rename 后没有 fsync 正确父目录，当前看似正确的运行可能在掉电后消失。恢复还必须清理残留，同时不能删除被引用 Artifact。

### 先看会坏在哪里

父链契约在创建 `one/two/three` 时记录 fsync，要求现有根目录和每个新目录的父级都出现。若只 fsync 最后一层，一个缺失的祖先目录项就可能让整棵子树在重启后不可达。

### 基本概念

目录保存名称到 inode 的映射。持久化文件内容不会自动持久化这个名称的创建或 rename。清理依据权威分类：临时名称和未引用 Artifact 可删除；Manifest 引用的 Artifact 必须保留。

### 为什么需要这个机制

崩溃安全是端到端顺序属性，不是“某处调用了 fsync”就够。记录精确父链并运行清理，能保护普通对象断言看不到的文件系统假设。

### 运行时心智模型

测试用 recorder 替换 `fsync_directory`，执行真实目录/存储创建，再断言父级顺序。另一个重启场景植入 stray 临时文件，重开存储后要求清理它，同时已发布对象仍可读取。

### 逐文件走读

#### `tests/test_storage.py`

##### 是什么，为什么现在需要

存储套件现在检查持久化调用与启动卫生，而不只检查逻辑对象值。

##### 在运行时做什么

Recorder 让不可见的文件系统义务变得可观察；重启场景按 Manifest 权威验证清理决策。

##### 关键代码

```python
assert calls == [tmp_path, tmp_path / "one", tmp_path / "one" / "two"]
```

##### 关键语句理解

每个新目录项存放在其父目录中，因此期望列表沿祖先链前进，而不是重复最终路径。这条断言锁定持久化链。

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

运行 `uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`。三个用例证明 atomic write、Bucket 创建的父链 fsync，以及安全删除 stray 临时文件。

### 需要真正记住的内容

文件字节、文件名和目录树各有持久化义务。恢复删除不权威内容，但绝不能删除 Manifest 仍引用的内容。

### 用自己的话讲清楚

MiniS3 通过 fsync 每个发生目录项变化的父目录，让发布跨掉电保存。启动时以 Manifest 为权威，保留被引用的不可变 Artifact，清除中断工作留下的临时或孤儿残留。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-07...stage-08)

完成后可运行 `git checkout stage-08` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/08-fsync-recovery/stage.patch)
