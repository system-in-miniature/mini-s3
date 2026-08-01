# Stage 12 · Multipart crash recovery

### Goal

Prove both sides of a completion crash: keep retryable staging before publish, clean it after publish.

### Hands-on task

Starting from stage-11, Exercise `_recover_uploads(...)` with crashes before and after manifest publication. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Mechanism walkthrough

#### Ownership and flow

This test-only stage correlates a published object's `multipart_upload_id` with private staging: retain staging before publish, clean it idempotently after publish.

#### Failure and debugging

After restart, inspect manifest visibility and upload-directory presence as one pair. Either both absent/present in the wrong crash window exposes a recovery bug.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `tests/test_storage.py`

Executable proof of the stage behavior.

Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

**Changed anchors:** `test_multipart_complete_crash_before_publish_keeps_upload_not_object`, `test_multipart_complete_crash_after_publish_recovers_object_and_cleans_upload`

??? note "File diff: tests/test_storage.py"
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

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Recovery correlates a published object with its upload ID to make cleanup idempotent.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`

### The real S3 lesson

Recovery correlates a published object with its upload ID to make cleanup idempotent.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-11...stage-12)

After finishing, use `git checkout stage-12` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/12-multipart-recovery/stage.patch)
