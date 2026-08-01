# Stage 08 · Directory fsync and startup cleanup

### Goal

Verify parent-directory durability and remove temporary or unreferenced crash debris on startup.

### Hands-on task

Starting from stage-07, Harden and test `atomic_write`, `durable_mkdir`, `DiskStorage.load_buckets`, and cleanup paths. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Mechanism walkthrough

#### Ownership and flow

This proof stage records directory fsync boundaries and creates interrupted-write debris, then checks that startup cleanup preserves referenced artifacts and removes temporary names.

#### Failure and debugging

Match every created or renamed directory entry with its parent fsync. During recovery, compare each deletion candidate against manifest references before removing it.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `tests/test_storage.py`

Executable proof of the stage behavior.

Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

**Changed anchors:** `test_atomic_write_fsyncs_each_new_directory_parent`, `recording_fsync_directory`, `test_storage_and_bucket_directory_creation_fsync_parent_chains`, `test_recovery_removes_spurious_tmp_files`

??? note "File diff: tests/test_storage.py"
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

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Atomic rename is not durable publication until the containing directory is fsynced.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`

### The real S3 lesson

Atomic rename is not durable publication until the containing directory is fsynced.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-07...stage-08)

After finishing, use `git checkout stage-08` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/08-fsync-recovery/stage.patch)
