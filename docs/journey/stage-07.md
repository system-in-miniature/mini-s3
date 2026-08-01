# Stage 07 · Manifest publication crash matrix

### Goal

Prove the manifest rename is the single visibility boundary by crashing immediately before and after it.

??? note "Deliverable files"
    - `tests/test_storage.py`

### The problem at this point

Stage 03 described publish-last storage, and clean restarts pass. That is not yet evidence that crashes expose only complete old or complete new states. The claim must be observed at each named crash boundary.

### Failure preview

One test injects `before_manifest_publish` after new artifacts are durable. Reopening must still return the old object and remove the unreferenced new artifact. If artifact existence alone controls visibility, the new value leaks despite the manifest never committing it.

### Test contract

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

**What this test locks**

The storage integration suite gains a parameterized crash matrix around artifact and manifest publication.

**How it constructs the counterexample**

It observes the system only after reopening, which discards misleading in-process memory and exercises recovery cleanup.

**Key test statement**

```python
crash_injector=CrashOnce("before_manifest_publish"),
```

**What a failure means**

The named hook fixes the exact interruption boundary. Assertions after a fresh open can therefore distinguish “artifacts durable” from “state published.”

### Basic concepts

A linearization point is the instant a concurrent or recovering observer treats an operation as having taken effect. A crash matrix probes both sides: before the point the old state wins; after the point the complete new state wins. There is no legal half-state.

### Why this mechanism is necessary

Documentation and happy-path tests cannot prove crash atomicity. Deliberate process-like interruption turns publication order into executable evidence and prevents a future refactor from moving visibility to artifact creation accidentally.

### Runtime mental model

The test prepares old state, installs `CrashOnce`, attempts a mutation, catches `InjectedCrash`, and constructs a fresh service. It then checks visible data and disk debris. The production code does not change in this stage; the new value is confidence in the existing boundary.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`. Five added cases cover multiple pre-publication points plus the post-publication side and cleanup.

### Durable takeaways

Artifact durability does not equal visibility. The manifest rename is the commit point: before it recovery selects old state, after it recovery selects complete new state.

### Explain it in your own words

The crash matrix proves atomicity by killing the operation on both sides of one named boundary and reopening from disk. Only the manifest makes immutable artifacts visible, so unreferenced files before publication are debris, while a published manifest after rename commits the complete new value.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-06...stage-07)

After finishing, use `git checkout stage-07` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/07-publication-crash-matrix/stage.patch)
