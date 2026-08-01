# Stage 15 · Public API and parity closeout

### Goal

Expose the complete teaching API and prove the reconstructed source and Journey-owned tests equal main byte for byte.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`

### Mechanism walkthrough

#### Ownership and flow

`minis3.__init__` is the supported adapter surface; the Journey builder then applies every patch and compares final `src/minis3` plus Journey-owned tests byte for byte with main. Site-only documentation tests stay outside this rebuild contract.

#### Failure and debugging

An import failure belongs to export wiring; a final parity failure names missing, extra, or changed files and must be fixed in the stage chain rather than hidden in generated commits.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `src/minis3/__init__.py`

Supported public package surface.

Reached by user imports; wiring errors appear as missing names before any runtime flow starts.

**Changed anchors:** configuration, export, or documentation change

??? note "File diff: src/minis3/__init__.py"
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

### Verification evidence

`uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)`

This stage adds no new behavior case: the cumulative suite guards the public exports, while `python journey/tools/build_journey.py --check` separately proves byte-for-byte final source and Journey-test parity.

### Concept check

Which invariant must remain true after this stage?

??? note "Answer"
    A rebuild journey stays trustworthy only when CI guards both behavior and final-source parity.

### Code-reading check

Start at `the public export list` in `src/minis3/__init__.py`: what state or value enters this boundary, and which owner consumes the result next?

??? note "Answer"
    Reached by user imports; wiring errors appear as missing names before any runtime flow starts.

### Interview-ready summary

A rebuild journey stays trustworthy only when CI guards both behavior and final-source parity.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/09-methodology.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-14...stage-15)

After finishing, use `git checkout stage-15` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/15-public-api-parity/stage.patch)
