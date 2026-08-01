# Stage 06 · Listing and the directory illusion / Listing 与目录幻觉

<!-- journey: chapter=4 tests_added=5 -->

## English

### Goal

Derive current contents and common prefixes from flat keys, with query-bound opaque pagination tokens.

### Deliverable files

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_listing.py`

### The problem at this point

Version listing can expose history, but normal object listing still has no answer for prefix, delimiter, or pagination. Treating slash-containing keys as real directories would contradict Stage 01 and create state that S3 does not store.

### Failure preview

The delimiter contract stores `a.txt`, `raw`, and several `photos/...` keys. Listing the root with delimiter `/` must return two contents plus exactly one `photos/` common prefix. If the implementation walks directories or returns every photo key, the externally visible projection is wrong.

### Basic concepts

`prefix` filters keys by exact string start. `delimiter` groups the remaining suffix at its first delimiter into a `common_prefix`; this is a computed view, not a stored folder. A page counts both returned objects and common prefixes because both consume result slots.

A continuation token is an opaque cursor. MiniS3 encodes the offset together with prefix and delimiter, so a token from one query cannot be replayed against another and silently skip different results.

### Why this mechanism is necessary

Exposing a raw numeric offset leaks implementation and allows query mismatch. Treating common prefixes as objects would confuse HEAD/GET and deletion. One pure projection keeps flat storage intact while producing familiar directory-like navigation.

### Runtime mental model

The service locks a Bucket snapshot and calls `list_objects`. The function selects each key's current visible data, applies prefix and delimiter projection, sorts the combined entries, decodes a query-bound offset, slices one page, and creates the next opaque token when more entries remain.

### File-by-file walkthrough

<!-- journey-file: src/minis3/listing.py -->
#### `src/minis3/listing.py`

##### What it is and why it appears

The read-side projection now owns current-object listing, delimiter grouping, and pagination tokens alongside version listing.

##### Runtime role

It consumes Bucket records without mutation and returns immutable `contents`, `common_prefixes`, and `next_token`.

##### Key code

```python
return urlsafe_b64encode(payload).decode().rstrip("=")
```

##### Statement understanding

The token hides the cursor representation. Its payload also contains the query shape, so decoding can reject a cursor that belongs to another prefix or delimiter.

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

The service adds the public locked entry for current listing.

##### Runtime role

It supplies one consistent records snapshot and delegates all read-only projection rules to `listing.py`.

##### Key code

```python
with self._lock:
```

##### Statement understanding

Even a pure projection needs a stable input snapshot. The lock prevents a concurrent PUT or DELETE from changing keys halfway through pagination construction.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

The package exports current-list response types together with the accumulated public API.

##### Runtime role

It keeps callers on one supported import surface; it does not calculate prefixes or tokens.

##### Statement understanding

The explicit `__all__` begins documenting which accumulated names are public rather than exporting every imported helper accidentally.

<!-- journey-file: tests/test_listing.py -->
#### `tests/test_listing.py`

##### What it is and why it appears

Five contracts cover directory illusion, combined pagination, marker hiding, flattened version history, and invalid tokens.

##### Runtime role

They build state through `MiniS3` and inspect public results, so the examples connect model semantics to the final read view.

##### Key code

```python
assert root.common_prefixes == ("photos/",)
```

##### Statement understanding

Several flat keys collapse into one projected prefix at the root. The tuple does not mean a `photos/` object or directory was stored.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/06-directory-illusion/tests.txt)`. The five new cases prove projection and token behavior while all earlier history tests remain cumulative.

### Durable takeaways

Keys stay flat; directories are a read-time illusion; contents and prefixes share page capacity; continuation tokens belong to one exact query.

### Explain it in your own words

MiniS3 produces directory-like listing by grouping flat strings at a delimiter. It never creates folders. Pagination operates on the combined projected result, and its opaque token is bound to the prefix and delimiter so it cannot be reused with different query semantics.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/04-listing.md)

## 中文

### 目标

从扁平 Key 推导当前 contents 与 common prefixes，并提供绑定查询的 opaque 分页 token。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_listing.py`

### 当前遇到的问题

版本 Listing 已能展示历史，但普通对象 Listing 仍不知道怎样处理 prefix、delimiter 和分页。把含斜杠 Key 当成真实目录会违背 Stage 01，并制造 S3 根本不存储的状态。

### 先看会坏在哪里

Delimiter 契约存入 `a.txt`、`raw` 和多个 `photos/...` Key。根目录用 `/` Listing 时必须返回两个 contents 和唯一的 `photos/` common prefix。如果实现遍历目录或返回所有 photo Key，公开投影就错了。

### 基本概念

`prefix` 按字符串开头过滤。`delimiter` 在剩余后缀第一次出现的位置分组出 `common_prefix`；它是计算视图，不是存储的文件夹。对象和 common prefix 都占结果槽位，所以分页必须共同计数。

Continuation token 是不透明游标。MiniS3 把 offset 与 prefix、delimiter 一起编码，避免把一个查询的 token 用到另一个查询后悄悄跳过不同结果。

### 为什么需要这个机制

暴露裸 offset 会泄漏实现并允许查询错配；把 common prefix 当对象则会混淆 HEAD/GET 与删除。单一纯投影既保持扁平存储，又提供熟悉的目录式浏览。

### 运行时心智模型

服务锁住 Bucket 快照并调用 `list_objects`。函数选择每个 Key 的当前可见数据，应用 prefix/delimiter 投影，对组合结果排序，解码绑定查询的 offset，截取一页，并在仍有结果时生成下一 token。

### 逐文件走读

<!-- journey-file: src/minis3/listing.py -->
#### `src/minis3/listing.py`

##### 是什么，为什么现在需要

读取侧现在除版本历史外，还拥有当前对象 Listing、delimiter 分组与分页 token。

##### 在运行时做什么

它不修改 Bucket records，返回不可变 `contents`、`common_prefixes` 与 `next_token`。

##### 关键代码

```python
return urlsafe_b64encode(payload).decode().rstrip("=")
```

##### 关键语句理解

编码隐藏游标表示；payload 还带查询形状，因此解码时能拒绝属于其他 prefix 或 delimiter 的游标。

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

服务增加当前 Listing 的公开带锁入口。

##### 在运行时做什么

它提供一致 records 快照，并把全部只读投影规则委托给 `listing.py`。

##### 关键代码

```python
with self._lock:
```

##### 关键语句理解

纯投影也需要稳定输入。锁防止并发 PUT/DELETE 在分页构造中途改变 Key 集合。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

包把当前 Listing 响应类型加入累积公开 API。

##### 在运行时做什么

调用方只需依赖一个受支持导入面；它不计算前缀或 token。

##### 关键语句理解

显式 `__all__` 开始记录累积的公开名称，避免意外导出全部内部 helper。

<!-- journey-file: tests/test_listing.py -->
#### `tests/test_listing.py`

##### 是什么，为什么现在需要

五条契约覆盖目录幻觉、组合分页、Marker 隐藏、版本展开和无效 token。

##### 在运行时做什么

它们通过 `MiniS3` 建立状态并观察公开结果，把模型语义连接到最终读取视图。

##### 关键代码

```python
assert root.common_prefixes == ("photos/",)
```

##### 关键语句理解

多个扁平 Key 在根视图中折叠成一个投影前缀；这个 tuple 不表示存储了 `photos/` 对象或目录。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-directory-illusion/tests.txt)`。五个新用例证明投影与 token 行为，所有早期历史测试继续累计执行。

### 需要真正记住的内容

Key 始终扁平；目录只是读取幻觉；contents 与 prefixes 共享页容量；continuation token 属于一个精确查询。

### 用自己的话讲清楚

MiniS3 通过在 delimiter 处对扁平字符串分组来展示类似目录的 Listing，从未创建文件夹。分页针对组合投影结果，opaque token 又绑定 prefix 与 delimiter，因此不能换一套查询语义继续使用。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/04-listing.md)
