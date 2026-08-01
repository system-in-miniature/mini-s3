# Stage 11 · Multipart 原子完成

### 目标

校验有序客户端清单、组装字节，并只发布一个可见对象。

### 交付文件

- `src/minis3/store.py`
- `tests/test_multipart.py`

### 机制走读

#### 所有权与数据流

完成操作加载私有 Part、校验有序客户端清单、拼接字节，通过普通 `Bucket.put` 只发布一次，最后删除暂存。

#### 失败与排查

先检查组装前校验，再检查清理前 Manifest 发布；出现部分可见对象说明发布被拆开，丢失重试状态说明清理过早。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/store.py`

协调领域逻辑与持久化的应用服务。

接收公开调用，拥有加锁与编排，再委托给领域、投影和存储边界。

**变化锚点:** `complete_multipart_upload`, `abort_multipart_upload`

??? note "文件差异：src/minis3/store.py"
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

#### `tests/test_multipart.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `_md5`, `test_multipart_is_invisible_until_ordered_atomic_complete`, `test_uploading_same_part_number_replaces_the_staged_part`, `test_complete_validates_order_presence_etag_and_nonfinal_size`, `test_abort_removes_upload_and_restart_preserves_unfinished_parts`, `test_upload_identity_and_part_number_are_validated`

??? note "文件差异：tests/test_multipart.py"
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

### 验证证据

`uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`

本阶段新增 4 个可执行用例，入口为 `test_multipart_is_invisible_until_ordered_atomic_complete`、`test_uploading_same_part_number_replaces_the_staged_part`、`test_complete_validates_order_presence_etag_and_nonfinal_size`、`test_abort_removes_upload_and_restart_preserves_unfinished_parts`。它们在机制走读之后运行，并与此前 Stage 的用例一起守住累计行为。

### 概念检查

本阶段完成后，哪条不变量必须保持成立？

??? note "答案"
    完成操作只通过与 PUT 相同的 Bucket manifest 发布边界变为可见。

### 代码阅读检查

从 `src/minis3/store.py` 的 `complete_multipart_upload` 开始：进入这个边界的状态或值是什么，结果又交给哪个所有者？

??? note "答案"
    接收公开调用，拥有加锁与编排，再委托给领域、投影和存储边界。

### 面试表达

完成操作只通过与 PUT 相同的 Bucket manifest 发布边界变为可见。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-10...stage-11)

完成后可运行 `git checkout stage-11` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/11-multipart-complete/stage.patch)
