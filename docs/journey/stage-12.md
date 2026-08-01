# Stage 12 · Multipart crash recovery

### Goal

Prove retryable staging before multipart publication and cleanup after publication.

??? note "Deliverable files"
    - `tests/test_storage.py`

### The problem at this point

Normal completion order is correct, but a crash can interrupt after assembly at either side of manifest publication. Recovery must not guess from the presence of staged files; it must correlate published object provenance with upload identity.

### Failure preview

The pre-publication test crashes completion at `before_manifest_publish`, reopens, and completes the same upload successfully. If recovery deletes all staging eagerly, the retry becomes impossible even though no object was committed.

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

**What it is and why it appears**

The storage recovery suite gains the two-sided multipart completion crash contract.

**Runtime role**

It uses fresh service instances to make published manifest and recovered staging—not stale memory—the only evidence.

**Key code**

```python
assert reopened.get_object("b", "movie").body == b"abcx"
```

**Statement understanding**

In the after-publish case, the visible complete object is authoritative even if cleanup did not run. Recovery must keep it and remove only the matching upload staging.

### Basic concepts

Before publication, staging is the only durable owner of the requested completion and must remain. After publication, the object version's `multipart_upload_id` proves that this upload committed, so leftover staging is redundant debris and may be removed.

### Why this mechanism is necessary

Using directory existence alone cannot distinguish an unfinished upload from post-commit cleanup interrupted by a crash. Correlating published provenance with upload ID makes both cases deterministic.

### Runtime mental model

Each test prepares a durable upload and parts, injects one crash point, discards the crashing service, and reopens. The before case retries completion; the after case reads the object and verifies abort now reports `NoSuchUpload` because recovery cleaned staging.

### Mechanism blocks

#### Multipart publication recovery

Prove completion crashes on either side of Manifest publication recover to exactly the old or new visible object state.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/12-multipart-recovery/tests.txt)`. Two tests prove both sides of completion publication and the cumulative suite guards ordinary crash behavior.

### Durable takeaways

Before commit, keep staging for retry. After commit, keep the object and remove matching staging. Published provenance disambiguates the two states.

### Explain it in your own words

Multipart recovery follows the same manifest commit point as normal objects, but uses upload provenance to clean correctly. A crash before publication leaves a retryable upload; a crash after publication leaves a complete object whose matching private staging is safe to discard.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-11...stage-12)

After finishing, use `git checkout stage-12` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/12-multipart-recovery/stage.patch)
