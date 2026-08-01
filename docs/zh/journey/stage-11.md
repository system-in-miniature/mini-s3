# Stage 11 · Multipart 原子完成

### 目标

校验有序完成清单、组装暂存字节，并只发布一个可见对象。

??? note "交付文件"
    - `src/minis3/store.py`
    - `tests/test_multipart.py`

### 当前遇到的问题

Part 已经持久但刻意不可见。完成操作必须把选中的私有 Part 变成一个普通版本，同时不能暴露中间字节、接受过期 receipt，或者在发布成功前删除可重试 Staging。

### 先看会坏在哪里

主契约上传两个 Part，并在完成前确认 List 为空。完成后要求 Body 为 `abcend`、ETag 是不同于 whole-body ETag 的两 Part 组合 ETag，并且只出现一个可见 Key。提前创建 ObjectRecord 或算错 ETag 都会直接暴露。

### 测试契约

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

**测试锁定什么**

四个场景覆盖完成前不可见、同编号替换、清单验证、Abort 和未完成上传重启。

**如何构造反例**

它们运行完整公开生命周期，同时观察可见对象与私有上传行为。

**关键测试语句**

```python
assert completed.etag != content_etag(completed.body)
```

**失败意味着什么**

这防止实现偷懒地把组装 Body 当普通 PUT 计算哈希；Multipart 身份来自 Part 摘要。

### 基本概念

完成是服务边界的一次有序事务：重载 Staging、校验客户端 receipt 列表、拼接选中字节、用组合 ETag 复用 Bucket PUT、发布候选 Bucket，最后删除 Staging。

Part 替换与完成分开。重传 Part 1 会改变当前 receipt；客户端用旧 ETag 完成时必须失败，不能拼装它没有确认的新字节。

### 为什么需要这个机制

逐 Part 发布会破坏 whole-object 可见性；Manifest 提交前删除 Staging 会摧毁重试能力。复用已有 Bucket 与 Manifest 路径，避免 Multipart 建立一套更弱的第二一致性模型。

### 运行时心智模型

`complete_multipart_upload` 持有服务锁，加载 upload 与 parts，调用纯 `validate_completion`，拼接 Body，用组合 ETag/来源修改候选 Bucket，持久化并替换内存，最后才删除上传目录。

### 机制板块

#### Multipart 原子完成

在一次带锁操作中校验回执、组装暂存字节、发布对象版本并移除上传状态。

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

**是什么，为什么现在需要**

服务增加完成编排，把私有 Staging 接到已有对象发布路径。

**在运行时做什么**

它拥有存储加载、纯验证、Bucket 变更、Manifest 发布与 Staging 清理之间的顺序。

**关键代码**

```python
self._storage.persist_bucket(candidate)
self._buckets[bucket] = candidate
self._storage.remove_multipart_upload(bucket, key, upload_id)
```

**关键语句理解**

清理必须最后执行。发布失败时上传仍可重试；发布成功后再删 Staging，也不会让已提交对象消失。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/11-multipart-complete/tests.txt)`。这些用例证明正常完成与验证；发布两侧的崩溃恢复由 Stage 12 单独锁定。

### 需要真正记住的内容

完成在变更前验证，只发布一个候选对象，并在提交后才清理 Staging；Multipart ETag 与 whole-body ETag 保持不同。

### 用自己的话讲清楚

MiniS3 把完成操作作为私有暂存 Part 到一个普通可见版本的桥梁。它校验客户端精确有序 receipt，组装字节，复用 Manifest 发布边界，并在尚未提交时保留 Staging 供重试。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-10...stage-11)

完成后可运行 `git checkout stage-11` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/11-multipart-complete/stage.patch)
