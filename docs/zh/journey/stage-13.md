# Stage 13 · 条件请求与 CAS

### 目标

把 ETag 用作缓存校验器，以及读取和变更的串行 compare-and-swap 前置条件。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/conditional.py`
- `src/minis3/errors.py`
- `src/minis3/store.py`
- `tests/test_conditional.py`

### 当前遇到的问题

系统已有 ETag，但调用方还不能要求“只在我看到的值仍是当前值时操作”。旧写入者可能覆盖新值，缓存也无法在不下载 Body 的情况下询问副本是否仍然有效。

### 先看会坏在哪里

并发契约让两个写入者携带相同初始 ETag。只能有一个通过 `If-Match`；第二个必须看到变化后的当前 ETag 并失败。如果检查在变更锁外，两者都可能校验旧状态并同时获胜。

### 基本概念

GET 的 `If-None-Match` 是缓存校验：匹配表示 representation 未修改（304 语义）。`If-Match` 是前置条件：不匹配表示请求不能作用于当前状态（412 语义）。

Compare-and-swap 表示“只有当前身份仍等于我观察到的身份才修改”。正确性依赖在同一串行临界区内完成检查和变更，而不只是比较字符串。

### 为什么需要这个机制

缺少前置条件时，read-modify-write 客户端会丢失更新。缺少不同的 304/412 失败，调用方无法区分缓存命中和变更被拒绝。集中匹配 helper 还能统一 wildcard 与逗号列表规则。

### 运行时心智模型

服务获得锁，解析当前或指定版本 ETag，执行 `require_if_match`/`require_if_none_match`，之后才读取或变更。成功 PUT 会在下一名等待写入者检查前改变 ETag。

### 逐文件走读

#### `src/minis3/conditional.py`

##### 是什么，为什么现在需要

这个纯策略模块解析 ETag 条件并抛出正确语义失败。

##### 在运行时做什么

Store 提供当前 ETag；helper 决定匹配、前置条件失败或未修改，不拥有锁和状态。

##### 关键代码

```python
if condition is not None and not etag_matches(condition, current_etag):
    raise PreconditionFailed(condition)
```

##### 关键语句理解

条件缺失表示不加 guard；条件存在但不匹配必须在变更前停止。只返回可能被调用方忽略的 `False` 会削弱契约。

??? note "文件差异：src/minis3/conditional.py"
    ```diff
    diff --git a/src/minis3/conditional.py b/src/minis3/conditional.py
    new file mode 100644
    index 0000000..d13ccf3
    --- /dev/null
    +++ b/src/minis3/conditional.py
    @@ -0,0 +1,35 @@
    +"""Pure HTTP-style ETag precondition evaluation.
    +
    +The service evaluates these functions while holding its mutation lock. That
    +placement matters: checking an ETag and publishing a replacement must be one
    +serialized compare-and-swap operation, not two individually safe calls.
    +"""
    +
    +from __future__ import annotations
    +
    +from .errors import NotModified, PreconditionFailed
    +
    +
    +def etag_matches(condition: str, current_etag: str | None) -> bool:
    +    """Return whether a simplified ETag header matches the current object."""
    +
    +    candidates = tuple(item.strip() for item in condition.split(","))
    +    if "*" in candidates:
    +        return current_etag is not None
    +    return current_etag is not None and current_etag in candidates
    +
    +
    +def require_if_match(current_etag: str | None, condition: str | None) -> None:
    +    """Raise S3's named 412 outcome when If-Match is not satisfied."""
    +
    +    if condition is not None and not etag_matches(condition, current_etag):
    +        raise PreconditionFailed(condition)
    +
    +
    +def require_if_none_match(
    +    current_etag: str | None, condition: str | None
    +) -> None:
    +    """Raise the body-less 304 control outcome when a cached ETag matches."""
    +
    +    if condition is not None and etag_matches(condition, current_etag):
    +        raise NotModified(condition)
    ```

#### `src/minis3/errors.py`

##### 是什么，为什么现在需要

失败词汇增加前置条件失败与未修改两个不同结果。

##### 在运行时做什么

协议适配器以后可分别映射 412 与 304，而领域服务无需嵌入 HTTP。

##### 关键代码

```python
class NotModified(MiniS3Error):
```

##### 关键语句理解

Not-modified 是校验器的控制流证据，不能和针对旧状态的变更拒绝混成同一错误。

??? note "文件差异：src/minis3/errors.py"
    ```diff
    diff --git a/src/minis3/errors.py b/src/minis3/errors.py
    index 9db3b4c..5f255e0 100644
    --- a/src/minis3/errors.py
    +++ b/src/minis3/errors.py
    @@ -43,3 +43,11 @@ class InvalidPartOrder(MiniS3Error):

     class EntityTooSmall(MiniS3Error):
         """A non-final multipart part is below the configured minimum size."""
    +
    +
    +class PreconditionFailed(MiniS3Error):
    +    """An If-Match condition failed (the S3-shaped HTTP 412 outcome)."""
    +
    +
    +class NotModified(MiniS3Error):
    +    """An If-None-Match condition matched (the HTTP 304 control outcome)."""
    ```

#### `src/minis3/store.py`

##### 是什么，为什么现在需要

公开 GET、PUT、DELETE 接受条件参数，并在已有锁内计算。

##### 在运行时做什么

它拥有当前 ETag 查找、前置条件决定与后续 Bucket 变更/发布之间的原子性。

##### 关键代码

```python
require_if_match(self._current_etag(candidate, key), if_match)
```

##### 关键语句理解

检查在服务锁内读取候选快照；从这行到变更之间，不会有其他写入者改变当前可见 ETag。

??? note "文件差异：src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index 9b50aa2..e47e1ac 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -8,8 +8,9 @@ from pathlib import Path
     from threading import RLock
     from time import time

    +from .conditional import require_if_match, require_if_none_match
     from .bucket import Bucket, SequenceCounter, VersioningState
    -from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
    +from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket, NoSuchKey, NoSuchVersion
     from .listing import ListObjectsResult, ListObjectVersionsResult, list_object_versions, list_objects
     from .model import ObjectVersion, Version
     from .multipart import (
    @@ -78,20 +79,39 @@ class MiniS3:
                 self._buckets[name] = candidate


    -    def put_object(self, bucket: str, key: str, body: bytes) -> Version:
    +    def put_object(
    +        self,
    +        bucket: str,
    +        key: str,
    +        body: bytes,
    +        *,
    +        if_match: str | None = None,
    +    ) -> Version:
             with self._lock:
                 candidate = deepcopy(self._bucket(bucket))
    -            result = candidate.put(key, body, self._counter)
    +            require_if_match(self._current_etag(candidate, key), if_match)
    +            result = candidate.put(
    +                key, body, self._counter, now=self._clock()
    +            )
                 self._storage.persist_bucket(candidate)
                 self._buckets[bucket] = candidate
                 return result


         def get_object(
    -        self, bucket: str, key: str, *, version_id: str | None = None
    +        self,
    +        bucket: str,
    +        key: str,
    +        *,
    +        version_id: str | None = None,
    +        if_match: str | None = None,
    +        if_none_match: str | None = None,
         ) -> Version:
             with self._lock:
    -            return self._bucket(bucket).get(key, version_id)
    +            result = self._bucket(bucket).get(key, version_id)
    +            require_if_match(result.etag, if_match)
    +            require_if_none_match(result.etag, if_none_match)
    +            return result


         def head_object(
    @@ -103,11 +123,21 @@ class MiniS3:


         def delete_object(
    -        self, bucket: str, key: str, *, version_id: str | None = None
    +        self,
    +        bucket: str,
    +        key: str,
    +        *,
    +        version_id: str | None = None,
    +        if_match: str | None = None,
         ) -> ObjectVersion | None:
             with self._lock:
                 candidate = deepcopy(self._bucket(bucket))
    -            result = candidate.delete(key, self._counter, version_id)
    +            require_if_match(
    +                self._addressed_etag(candidate, key, version_id), if_match
    +            )
    +            result = candidate.delete(
    +                key, self._counter, version_id, now=self._clock()
    +            )
                 self._storage.persist_bucket(candidate)
                 self._buckets[bucket] = candidate
                 return result
    @@ -220,6 +250,24 @@ class MiniS3:
                 self._storage.remove_multipart_upload(bucket, key, upload_id)


    +    @staticmethod
    +    def _current_etag(bucket: Bucket, key: str) -> str | None:
    +        try:
    +            return bucket.get(key).etag
    +        except NoSuchKey:
    +            return None
    +
    +
    +    @staticmethod
    +    def _addressed_etag(
    +        bucket: Bucket, key: str, version_id: str | None
    +    ) -> str | None:
    +        try:
    +            return bucket.get(key, version_id).etag
    +        except (NoSuchKey, NoSuchVersion):
    +            return None
    +
    +
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
    ```

#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

条件请求失败成为受支持 API。

##### 在运行时做什么

调用方从包根捕获语义结果，匹配 helper 继续作为内部策略。

##### 关键语句理解

公开结果类型但不公开解析内部细节，可以保持 API 较小。

??? note "文件差异：src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 0c23aea..3f6e582 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -7,3 +7,4 @@ from .storage import InjectedCrash
     from .listing import ListedObject, ListedVersion, ListObjectsResult, ListObjectVersionsResult
     from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder, NoSuchUpload
     from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
    +from .errors import NotModified, PreconditionFailed
    ```

#### `tests/test_conditional.py`

##### 是什么，为什么现在需要

四条契约覆盖 GET 校验、变更 guard、wildcard 和双写者 CAS 竞争。

##### 在运行时做什么

线程测试证明顺序 helper 单测无法证明的串行化行为。

##### 关键代码

```python
assert sorted(outcomes) == ["412", "stored"]
```

##### 关键语句理解

一个 `stored` 与一个 `412` 是外部可见 CAS 保证；两个 stored 会证明检查与变更并不原子。

??? note "文件差异：tests/test_conditional.py"
    ```diff
    diff --git a/tests/test_conditional.py b/tests/test_conditional.py
    new file mode 100644
    index 0000000..137e7a1
    --- /dev/null
    +++ b/tests/test_conditional.py
    @@ -0,0 +1,81 @@
    +"""Conditional requests turn current ETags into an object-level CAS token."""
    +
    +from concurrent.futures import ThreadPoolExecutor
    +from pathlib import Path
    +from threading import Barrier
    +
    +import pytest
    +
    +from minis3 import MiniS3, NoSuchKey, NotModified, PreconditionFailed
    +
    +
    +def test_get_if_none_match_has_304_semantics_and_if_match_has_412(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    current = store.put_object("b", "k", b"value")
    +
    +    with pytest.raises(NotModified):
    +        store.get_object("b", "k", if_none_match=current.etag)
    +    with pytest.raises(NotModified):
    +        store.get_object("b", "k", if_none_match="*")
    +    with pytest.raises(PreconditionFailed):
    +        store.get_object(
    +            "b", "k", if_match='"00000000000000000000000000000000"'
    +        )
    +    assert store.get_object("b", "k", if_match=current.etag) == current
    +
    +
    +def test_put_and_delete_if_match_compare_against_current_visible_etag(
    +    tmp_path: Path,
    +) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    initial = store.put_object("b", "k", b"old")
    +    winner = store.put_object("b", "k", b"new", if_match=initial.etag)
    +
    +    with pytest.raises(PreconditionFailed):
    +        store.put_object("b", "k", b"stale", if_match=initial.etag)
    +    with pytest.raises(PreconditionFailed):
    +        store.delete_object("b", "k", if_match=initial.etag)
    +
    +    removed = store.delete_object("b", "k", if_match=winner.etag)
    +    assert removed is None
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("b", "k")
    +
    +
    +def test_if_match_wildcard_requires_a_current_visible_object(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +
    +    with pytest.raises(PreconditionFailed):
    +        store.put_object("b", "missing", b"x", if_match="*")
    +    with pytest.raises(PreconditionFailed):
    +        store.delete_object("b", "missing", if_match="*")
    +
    +    store.put_object("b", "present", b"x")
    +    assert store.put_object("b", "present", b"y", if_match="*").body == b"y"
    +
    +
    +def test_two_conditional_writers_have_exactly_one_winner(tmp_path: Path) -> None:
    +    store = MiniS3(tmp_path)
    +    store.create_bucket("b")
    +    observed = store.put_object("b", "counter", b"0").etag
    +    barrier = Barrier(2)
    +
    +    def writer(value: bytes) -> str:
    +        barrier.wait()
    +        try:
    +            store.put_object("b", "counter", value, if_match=observed)
    +        except PreconditionFailed:
    +            return "412"
    +        return "stored"
    +
    +    with ThreadPoolExecutor(max_workers=2) as pool:
    +        outcomes = list(pool.map(writer, (b"writer-a", b"writer-b")))
    +
    +    assert sorted(outcomes) == ["412", "stored"]
    +    assert store.get_object("b", "counter").body in {b"writer-a", b"writer-b"}
    +
    ```

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`。用例证明匹配形式、失败含义、变更 guard 和单赢家并发。

### 需要真正记住的内容

ETag 比较只有在检查与变更共享同一把锁时才成为安全并发控制；304 校验与 412 拒绝是不同结果。

### 用自己的话讲清楚

条件请求让调用方只对自己观察过的精确值采取行动。MiniS3 在服务变更锁内计算 ETag guard，所以一名写入者提交后，所有旧竞争者会面对新的当前 ETag 失败，而不是覆盖它。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/07-conditional.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-12...stage-13)

完成后可运行 `git checkout stage-13` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/13-conditional-cas/stage.patch)
