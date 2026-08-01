# Stage 07 · Manifest publication crash matrix

### Goal

Pin the manifest rename as the linearization point by crashing immediately before and after it.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Mechanism walkthrough

#### Ownership and flow

This stage changes tests, not production code. Fault injection brackets manifest replacement to prove the old/new visibility split around one linearization point.

#### Failure and debugging

Reopen storage after each injected crash and inspect only published state. Seeing partial new state means publication order or recovery trust boundaries are wrong.

### File-by-file diff walkthrough

Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`.

#### `tests/test_storage.py`

Executable proof of the stage behavior.

Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

**Changed anchors:** `test_crash_before_manifest_publish_leaves_old_state`, `test_crash_before_manifest_publication_matrix_leaves_old_state`, `test_crash_after_manifest_publish_exposes_complete_new_state`

??? note "File diff: tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    index c96a7a6..5faad97 100644
    --- a/tests/test_storage.py
    +++ b/tests/test_storage.py
    @@ -30,3 +30,69 @@ def test_restart_restores_versions_bodies_and_counter(tmp_path: Path) -> None:

         assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
         assert second.version_id != first.version_id
    +
    +
    +def test_crash_before_manifest_publish_leaves_old_state(tmp_path: Path) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    crashing = MiniS3(
    +        tmp_path,
    +        counter=SequenceCounter(10),
    +        crash_injector=CrashOnce("before_manifest_publish"),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.put_object("b", "new", b"value")
    +
    +    reopened = MiniS3(tmp_path)
    +    with pytest.raises(NoSuchKey):
    +        reopened.get_object("b", "new")
    +    assert not list(tmp_path.rglob("*.tmp-*"))
    +    assert not list(tmp_path.rglob("e00000010.*"))
    +
    +
    +@pytest.mark.parametrize(
    +    "crash_point",
    +    [
    +        "after_object_directory_create",
    +        "after_object_directory_parent_fsync",
    +        "before_manifest_publish",
    +    ],
    +)
    +def test_crash_before_manifest_publication_matrix_leaves_old_state(
    +    tmp_path: Path,
    +    crash_point: str,
    +) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    crashing = MiniS3(
    +        tmp_path,
    +        counter=SequenceCounter(10),
    +        crash_injector=CrashOnce(crash_point),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.put_object("b", "new", b"value")
    +
    +    reopened = MiniS3(tmp_path)
    +    with pytest.raises(NoSuchKey):
    +        reopened.get_object("b", "new")
    +    assert not list(tmp_path.rglob("*.tmp-*"))
    +    assert not list(tmp_path.rglob("e00000010.*"))
    +
    +
    +def test_crash_after_manifest_publish_exposes_complete_new_state(
    +    tmp_path: Path,
    +) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    crashing = MiniS3(
    +        tmp_path,
    +        counter=SequenceCounter(10),
    +        crash_injector=CrashOnce("after_manifest_publish"),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.put_object("b", "new", b"value")
    +
    +    reopened = MiniS3(tmp_path)
    +    visible = reopened.get_object("b", "new")
    +    assert visible.body == b"value"
    +    assert visible.etag == '"2063c1608d6e0baf80249c42e2be5804"'
    ```

### Verification evidence

`uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`

This stage adds 5 executable case(s), anchored at `test_crash_before_manifest_publish_leaves_old_state`, `test_crash_before_manifest_publication_matrix_leaves_old_state`, `test_crash_after_manifest_publish_exposes_complete_new_state`. Run them after the mechanism walkthrough; the cumulative gate also reruns every earlier stage contract.

### Concept check

Which invariant must remain true after this stage?

??? note "Answer"
    Before rename, recovery sees the old state; after rename, it sees the complete new state.

### Code-reading check

Start at `test_crash_before_manifest_publish_leaves_old_state` in `tests/test_storage.py`: what state or value enters this boundary, and which owner consumes the result next?

??? note "Answer"
    Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.

### Interview-ready summary

Before rename, recovery sees the old state; after rename, it sees the complete new state.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-06...stage-07)

After finishing, use `git checkout stage-07` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/07-publication-crash-matrix/stage.patch)
