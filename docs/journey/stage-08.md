# Stage 08 · Directory fsync and startup cleanup

### Goal

Verify directory-entry durability and recovery cleanup for temporary and unreferenced crash debris.

??? note "Deliverable files"
    - `tests/test_storage.py`

### The problem at this point

The crash matrix proves which manifest is visible, but durability also depends on directory entries. Creating nested directories or renaming a file without fsyncing the right parent can make a correct-looking run disappear after power loss. Recovery must also remove debris without deleting referenced artifacts.

### Failure preview

The parent-chain contract records fsync calls while creating `one/two/three`. It expects calls for the existing root and each newly created directory's parent. If only the final directory is fsynced, one missing ancestor entry can make the whole subtree unreachable after restart.

### Basic concepts

A directory stores name-to-inode mappings. Persisting file contents does not automatically persist creation or rename of that name. Cleanup classifies files by authority: temporary names and unreferenced artifacts may be removed; manifest-referenced artifacts must remain.

### Why this mechanism is necessary

Crash safety is an end-to-end ordering property, not merely a call to `fsync` somewhere. Recording the exact parent chain and exercising cleanup protects the subtle filesystem assumptions that ordinary object assertions cannot see.

### Runtime mental model

Tests replace `fsync_directory` with a recorder, perform real directory/storage creation, and assert the ordered parents. A separate restart case plants a stray temporary file, reopens storage, and requires cleanup while the published object remains readable.

### File-by-file walkthrough

#### `tests/test_storage.py`

##### What it is and why it appears

The storage suite now inspects durability calls and startup hygiene, not just logical object values.

##### Runtime role

Its recorder makes invisible filesystem obligations observable; its restart case verifies cleanup decisions against manifest authority.

##### Key code

```python
assert calls == [tmp_path, tmp_path / "one", tmp_path / "one" / "two"]
```

##### Statement understanding

Each new directory entry lives in its parent, so the expected list walks the ancestry rather than repeating the final path. This assertion locks the durability chain.

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

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/08-fsync-recovery/tests.txt)`. Three cases prove parent-chain fsync behavior for atomic writes and Bucket creation plus safe removal of stray temporary files.

### Durable takeaways

File bytes, file names, and directory trees have separate durability obligations. Recovery removes what is not authoritative, never what the manifest still references.

### Explain it in your own words

MiniS3 makes publication survive power loss by fsyncing every parent whose directory entries changed. On startup it treats the manifest as authority, preserving referenced immutable artifacts and deleting temporary or orphaned debris left by interrupted work.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-07...stage-08)

After finishing, use `git checkout stage-08` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/08-fsync-recovery/stage.patch)
