# Stage 11 · Atomic multipart completion

### Goal

Validate an ordered completion manifest, assemble staged bytes, and publish exactly one visible object.

??? note "Deliverable files"
    - `src/minis3/store.py`
    - `tests/test_multipart.py`

### The problem at this point

Parts are durable but intentionally invisible. Completion must turn selected private parts into one normal version without exposing intermediate bytes, accepting stale receipts, or deleting retryable staging before publication succeeds.

### Test contract

#### See the failure first

The main contract uploads two parts and confirms List is empty before completion. After completion it requires body `abcend`, a two-part composite ETag different from the whole-body ETag, and exactly one visible key. Any early ObjectRecord or wrong ETag is immediately visible.

??? note "File diff: tests/test_multipart.py"
    ```diff
    diff --git a/tests/test_multipart.py b/tests/test_multipart.py
    index 0b61034..adcb3f7 100644
    --- a/tests/test_multipart.py
    +++ b/tests/test_multipart.py
    @@ -17,6 +17,104 @@ from minis3 import (
     )


    +def _md5(payload: bytes) -> bytes:
    +    return md5(payload, usedforsecurity=False).digest()
    +
    +
    +def test_multipart_is_invisible_until_ordered_atomic_complete(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path, counter=SequenceCounter(), minimum_part_size=3)
    +    store.create_bucket("b")
    +    upload = store.create_multipart_upload("b", "movie")
    +    second = store.upload_part("b", "movie", upload.upload_id, 2, b"end")
    +    first = store.upload_part("b", "movie", upload.upload_id, 1, b"abc")
    +
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("b", "movie")
    +    assert store.list_objects("b").contents == ()
    +
    +    completed = store.complete_multipart_upload(
    +        "b", "movie", upload.upload_id, [first, second]
    +    )
    +
    +    expected = md5(_md5(b"abc") + _md5(b"end"), usedforsecurity=False).hexdigest()
    +    assert completed.body == b"abcend"
    +    assert completed.etag == f'"{expected}-2"'
    +    assert completed.etag != content_etag(completed.body)
    +    assert [item.key for item in store.list_objects("b").contents] == ["movie"]
    +
    +
    +def test_uploading_same_part_number_replaces_the_staged_part(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path, minimum_part_size=3)
    +    store.create_bucket("b")
    +    upload = store.create_multipart_upload("b", "k")
    +    store.upload_part("b", "k", upload.upload_id, 1, b"old")
    +    first = store.upload_part("b", "k", upload.upload_id, 1, b"new")
    +    last = store.upload_part("b", "k", upload.upload_id, 2, b"x")
    +
    +    completed = store.complete_multipart_upload(
    +        "b", "k", upload.upload_id, [first, last]
    +    )
    +
    +    assert completed.body == b"newx"
    +
    +
    +def test_complete_validates_order_presence_etag_and_nonfinal_size(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path, minimum_part_size=3)
    +    store.create_bucket("b")
    +    upload = store.create_multipart_upload("b", "k")
    +    small = store.upload_part("b", "k", upload.upload_id, 1, b"x")
    +    final = store.upload_part("b", "k", upload.upload_id, 2, b"last")
    +
    +    with pytest.raises(InvalidPartOrder):
    +        store.complete_multipart_upload(
    +            "b", "k", upload.upload_id, [final, small]
    +        )
    +    with pytest.raises(InvalidPart):
    +        store.complete_multipart_upload(
    +            "b",
    +            "k",
    +            upload.upload_id,
    +            [(1, '"00000000000000000000000000000000"'), final],
    +        )
    +    with pytest.raises(InvalidPart):
    +        store.complete_multipart_upload(
    +            "b", "k", upload.upload_id, [(3, final.etag)]
    +        )
    +    with pytest.raises(EntityTooSmall):
    +        store.complete_multipart_upload(
    +            "b", "k", upload.upload_id, [small, final]
    +        )
    +
    +    # A small part is legal when the completion manifest makes it the last.
    +    completed = store.complete_multipart_upload(
    +        "b", "k", upload.upload_id, [small]
    +    )
    +    assert completed.body == b"x"
    +
    +
    +def test_abort_removes_upload_and_restart_preserves_unfinished_parts(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path, minimum_part_size=3)
    +    store.create_bucket("b")
    +    upload = store.create_multipart_upload("b", "k")
    +    first = store.upload_part("b", "k", upload.upload_id, 1, b"abc")
    +
    +    reopened = MiniS3(tmp_path, minimum_part_size=3)
    +    last = reopened.upload_part("b", "k", upload.upload_id, 2, b"x")
    +    reopened.abort_multipart_upload("b", "k", upload.upload_id)
    +
    +    with pytest.raises(NoSuchUpload):
    +        reopened.complete_multipart_upload(
    +            "b", "k", upload.upload_id, [first, last]
    +        )
    +    assert not list(tmp_path.rglob(upload.upload_id))
    +
    +
     def test_upload_identity_and_part_number_are_validated(tmp_path: Path) -> None:
         store = MiniS3(tmp_path)
         store.create_bucket("b")
    @@ -28,3 +126,4 @@ def test_upload_identity_and_part_number_are_validated(tmp_path: Path) -> None:
             store.upload_part("b", "right", upload.upload_id, 0, b"x")
         with pytest.raises(ValueError):
             store.upload_part("b", "right", upload.upload_id, 10_001, b"x")
    +
    ```

**What this test locks**

Four cases cover invisibility until completion, same-number replacement, manifest validation, abort, and restart of unfinished staging.

**How it constructs the counterexample**

They exercise the complete public lifecycle and inspect both visible objects and private upload behavior.

**Key test statement**

```python
assert completed.etag != content_etag(completed.body)
```

**What a failure means**

This prevents an easy but incorrect implementation from hashing assembled bytes as a normal PUT. Multipart identity is derived from part digests.

### Basic concepts

Completion is one ordered transaction at the service boundary: reload staging, validate the client's receipt list, concatenate selected bytes, reuse Bucket PUT with the composite ETag, publish the candidate Bucket, then remove staging.

Part replacement and completion are separate. Re-uploading part 1 changes the current receipt; a client that completes with the old ETag must fail rather than assemble unexpected bytes.

### Why this mechanism is necessary

Publishing each part would violate whole-object visibility. Removing staging before the manifest commits destroys retryability. Reusing the established Bucket and manifest path keeps multipart from creating a weaker second consistency model.

### Runtime mental model

`complete_multipart_upload` holds the service lock, loads upload plus parts, calls pure `validate_completion`, joins bodies, mutates a candidate Bucket with composite ETag/provenance, persists it, swaps it into memory, and only then removes the upload directory.

### Mechanism blocks

#### Atomic multipart completion

Validate receipts, assemble staged bytes, publish one object version, and remove upload state as one locked operation.

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index 0d7e596..9b50aa2 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -177,6 +177,39 @@ class MiniS3:
                 return part.receipt


    +    def complete_multipart_upload(
    +        self,
    +        bucket: str,
    +        key: str,
    +        upload_id: str,
    +        parts: list[CompletionEntry] | tuple[CompletionEntry, ...],
    +    ) -> Version:
    +        """Validate, assemble, and publish through the bucket manifest rename."""
    +
    +        with self._lock:
    +            self._bucket(bucket)
    +            _upload, staged = self._storage.load_multipart_upload(
    +                bucket, key, upload_id
    +            )
    +            selected, etag = validate_completion(
    +                staged, parts, minimum_part_size=self.minimum_part_size
    +            )
    +            body = b"".join(part.body for part in selected)
    +            candidate = deepcopy(self._bucket(bucket))
    +            result = candidate.put(
    +                key,
    +                body,
    +                self._counter,
    +                etag=etag,
    +                now=self._clock(),
    +                multipart_upload_id=upload_id,
    +            )
    +            self._storage.persist_bucket(candidate)
    +            self._buckets[bucket] = candidate
    +            self._storage.remove_multipart_upload(bucket, key, upload_id)
    +            return result
    +
    +
         def abort_multipart_upload(
             self, bucket: str, key: str, upload_id: str
         ) -> None:
    ```

**What it is and why it appears**

The service gains the completion orchestration that connects private staging to the existing object publication path.

**Runtime role**

It owns the ordering across storage load, pure validation, Bucket mutation, manifest publication, and staging cleanup.

**Key code**

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
self._storage.remove_multipart_upload(bucket, key, upload_id)
```

**Statement understanding**

Cleanup is last. If publication fails, the upload remains retryable; once publication succeeds, removing staging cannot make the committed object disappear.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`. The cases prove normal completion and validation. Crash recovery on either side of publication is isolated in Stage 12.

### Durable takeaways

Completion validates before mutation, publishes one candidate object, and cleans staging only after commit. Multipart ETag remains distinct from whole-body ETag.

### Explain it in your own words

MiniS3 treats completion as the bridge from private staged parts to one ordinary visible version. It validates the client's exact ordered receipts, assembles bytes, uses the established manifest publication boundary, and retains staging whenever publication has not committed.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-10...stage-11)

After finishing, use `git checkout stage-11` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/11-multipart-complete/stage.patch)
