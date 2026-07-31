# Stage 07 · Manifest publication crash matrix

### Goal

Pin the manifest rename as the linearization point by crashing immediately before and after it.

### Hands-on task

Starting from stage-06, Exercise `DiskStorage.persist_bucket` through `CrashOnce` at every publication boundary. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `tests/test_storage.py`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        Before rename, recovery sees the old state; after rename, it sees the complete new state.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`

### The real S3 lesson

Before rename, recovery sees the old state; after rename, it sees the complete new state.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-06...stage-07)

After finishing, use `git checkout stage-07` to compare your result.

??? note "Try first, then peek: stage.patch"
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
