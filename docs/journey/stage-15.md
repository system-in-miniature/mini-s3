# Stage 15 · Public API and parity closeout

### Goal

Expose the complete teaching API and prove the stage-built source and Journey tests match main byte for byte.

??? note "Deliverable files"
    - `src/minis3/__init__.py`

### The problem at this point

All mechanisms exist, but accumulated imports can still expose accidental names or omit intended ones. Passing behavioral tests also does not by itself prove the Journey reconstructs the exact maintained source and test corpus.

### Failure preview

The parity command rebuilds every patch into a fresh tree and compares bytes with main. One missing export line or stale stage test makes the check fail even if a narrow pytest selection remains green. This catches drift between the learning path and finished repository.

### Basic concepts

A public API is an intentional compatibility boundary, not every name currently importable from a module. `__all__` records that choice. Source parity and behavioral evidence are complementary: tests prove selected semantics; byte comparison proves the reconstruction artifact is the maintained artifact.

### Why this mechanism is necessary

A course can slowly become a detached toy while its examples still pass. Closing with exact exports and byte parity makes source alignment an enforceable property rather than a README claim.

### Runtime mental model

User imports resolve through `src/minis3/__init__.py`. Separately, `build_journey.py --check` starts from the empty Journey root, applies all 15 canonical patches, gathers Journey-owned tests, and compares reconstructed bytes to the current main tree without moving refs.

### File-by-file walkthrough

#### `src/minis3/__init__.py`

##### What it is and why it appears

The package root receives its final explicit export list for values, services, policies, results, and public failures.

##### Runtime role

It is the stable learner-facing import boundary. Internal storage helpers and implementation-only functions remain absent.

##### Key code

```python
__all__ = [
```

##### Statement understanding

The list converts an implicit collection of imports into a deliberate contract. Adding an internal helper elsewhere no longer makes it public accidentally.

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

Run `uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)` for the cumulative suite, then `python journey/tools/build_journey.py --check` for byte-for-byte source and Journey-test parity. Stage 15 adds no new behavior case because its deliverable is the public surface and reconstruction proof.

### Durable takeaways

An import surface, passing tests, and byte parity prove different things. Completion requires all three to agree with the intended course boundary.

### Explain it in your own words

The final Stage makes the learning journey auditable. `__all__` states which concepts are supported publicly, cumulative tests prove their behavior, and the parity rebuild proves the sequence of stages reconstructs the same source and tests maintained on main.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/09-methodology.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-14...stage-15)

After finishing, use `git checkout stage-15` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/15-public-api-parity/stage.patch)
