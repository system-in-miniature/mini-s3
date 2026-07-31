# Stage 08 · 目录 fsync 与启动清理

### 目标

验证父目录持久性，并在启动时清理临时或未引用的崩溃残留。

### 动手任务

从stage-07开始，强化并测试 `atomic_write`、`durable_mkdir`、`DiskStorage.load_buckets` 与清理路径。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `tests/test_storage.py`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        只有对所在目录执行 fsync，原子 rename 才成为持久发布。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`

### 对应真实 S3 的一课

只有对所在目录执行 fsync，原子 rename 才成为持久发布。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-07...stage-08)

完成后可运行 `git checkout stage-08` 对照你的结果。

??? note "先做后看：stage.patch"
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
