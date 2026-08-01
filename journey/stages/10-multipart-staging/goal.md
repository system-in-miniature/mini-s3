# Stage 10 · Durable multipart staging / Multipart 持久暂存

<!-- journey: chapter=6 tests_added=1 -->

## English

### Goal

Persist private multipart uploads and atomically replace parts without publishing an object.

### Deliverable files

- `src/minis3/__init__.py`
- `src/minis3/bucket.py`
- `src/minis3/model.py`
- `src/minis3/storage/disk.py`
- `src/minis3/store.py`
- `tests/test_multipart.py`

### The problem at this point

Stage 09 validates abstract staged parts, but a real client needs upload IDs and part bytes to survive retries and restarts. Those bytes must remain invisible to normal GET/List until completion publishes exactly one object.

### Test contract

#### See the failure first

The first integration contract creates an upload for key `right`, then tries to upload through key `wrong` and through part numbers `0` and `10001`. Each request must fail before writing staging. Otherwise an upload ID can be confused across keys or create invalid part files.

<!-- journey-file: tests/test_multipart.py -->
#### `tests/test_multipart.py`

##### What it is and why it appears

The first durable multipart test locks upload identity and legal part-number range.

##### Runtime role

It enters through `MiniS3`, so failures cover service validation plus storage identity lookup.

##### Key code

```python
store.upload_part("b", "wrong", upload.upload_id, 1, b"x")
```

##### Statement understanding

An upload ID is not globally interchangeable: the addressed Bucket and Key must match its persisted metadata before any part is written.

### Basic concepts

Staging is durable private state, not a partially visible object. Each upload has identity `(bucket, key, upload_id)` and its own `parts/` directory. Re-uploading the same part number atomically replaces that staged slot.

The object model gains creation time and optional `multipart_upload_id` provenance for a future completed version. These fields do not make staging visible; only an `ObjectRecord` referenced by the Bucket manifest does that.

### Why this mechanism is necessary

Keeping parts only in memory makes retry and restart unreliable. Writing them directly into object history exposes incomplete values. A separate durable namespace preserves work while maintaining the one publication boundary established earlier.

### Runtime mental model

The service allocates a deterministic upload ID and asks DiskStorage to create `uploads/<id>/upload.json` plus `parts/`. `upload_part` validates the number and upload identity, then atomically writes one numbered `.data` file. Abort removes only that private upload directory.

### Mechanism blocks

<!-- journey-file: src/minis3/model.py -->
#### `src/minis3/model.py`

##### What it is and why it appears

Versions and markers gain timestamps; data versions can record which multipart upload produced them after completion.

##### Runtime role

Lifecycle and recovery will consume these fields later. They remain immutable metadata attached to published history.

##### Key code

```python
multipart_upload_id: str | None = None
```

##### Statement understanding

`None` identifies normal PUTs; a completed multipart version can retain provenance without turning the upload itself into visible history.

<!-- journey-file: src/minis3/bucket.py -->
#### `src/minis3/bucket.py`

##### What it is and why it appears

Bucket PUT accepts an optional externally calculated ETag, timestamp, and multipart provenance while keeping normal PUT defaults.

##### Runtime role

Completion will reuse the same version transition rather than inventing a second publication path.

##### Key code

```python
etag=content_etag(body) if etag is None else etag,
```

##### Statement understanding

Normal PUT still derives a whole-body ETag; multipart completion can supply its validated composite ETag. Recomputing it from assembled bytes would be wrong.

<!-- journey-file: src/minis3/storage/disk.py -->
#### `src/minis3/storage/disk.py`

##### What it is and why it appears

DiskStorage gains the private upload layout, atomic part writes, identity validation, removal, and restart recovery.

##### Runtime role

It owns durable staging just as it owns durable object artifacts, but normal manifest/list code never consults `uploads/`.

##### Key code

```python
atomic_write(directory / "parts" / f"{part.part_number:05d}.data", part.body)
```

##### Statement understanding

The part number selects one stable filename and `atomic_write` replaces it completely. A retry cannot leave half old and half new bytes.

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

The public service adds initiate, upload-part, and abort orchestration with an injectable clock and minimum part size.

##### Runtime role

It validates public parameters under the same lock, allocates deterministic upload identity, and delegates private bytes to DiskStorage.

##### Key code

```python
upload_id=f"u{sequence:08d}",
```

##### Statement understanding

Upload IDs share the monotonic sequence discipline, making restart recovery and teaching traces deterministic instead of relying on random UUIDs.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

Multipart values and failures join the supported package API.

##### Runtime role

Callers can hold upload receipts and catch `NoSuchUpload` without importing storage internals.

##### Statement understanding

The exports expose domain contracts, not the private disk layout.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/10-multipart-staging/tests.txt)`. It proves identity and range rejection while cumulative tests protect earlier object behavior. Completion visibility is deliberately deferred.

### Durable takeaways

Staging is durable but private; upload identity includes Bucket and Key; same-number retries replace atomically; only Bucket manifest publication creates an object.

### Explain it in your own words

MiniS3 stores incomplete multipart work in a separate durable namespace. The service validates upload identity and part numbers, while DiskStorage atomically replaces numbered part files. Normal GET and List remain unchanged because no ObjectRecord is published yet.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/06-multipart.md)

## 中文

### 目标

持久化私有 Multipart 上传并原子替换 Part，同时不发布对象。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/bucket.py`
- `src/minis3/model.py`
- `src/minis3/storage/disk.py`
- `src/minis3/store.py`
- `tests/test_multipart.py`

### 当前遇到的问题

Stage 09 只能验证抽象暂存 Part；真实客户端需要 upload ID 和 Part 字节跨重试、重启保存。这些字节在完成发布一个完整对象以前，必须对普通 GET/List 不可见。

### 测试契约

#### 先看会坏在哪里

第一条集成契约为 Key `right` 创建上传，再尝试用 Key `wrong` 和 Part 编号 `0`、`10001` 上传。每次都必须在写暂存前失败，否则 upload ID 会跨 Key 混用或产生非法 Part 文件。

<!-- journey-file: tests/test_multipart.py -->
#### `tests/test_multipart.py`

##### 是什么，为什么现在需要

第一条持久 Multipart 测试锁定上传身份和合法 Part 编号范围。

##### 在运行时做什么

它通过 `MiniS3` 进入，因此失败同时覆盖服务校验与存储身份查找。

##### 关键代码

```python
store.upload_part("b", "wrong", upload.upload_id, 1, b"x")
```

##### 关键语句理解

Upload ID 不能全局互换：寻址的 Bucket 与 Key 必须和持久元数据匹配，之后才能写 Part。

### 基本概念

Staging 是持久私有状态，不是部分可见对象。每次上传由 `(bucket, key, upload_id)` 标识，并拥有自己的 `parts/` 目录；重复上传相同 Part 编号会原子替换这个暂存槽。

对象模型增加创建时间和可选 `multipart_upload_id` 来源，供未来完成后的版本记录。这些字段不会让 Staging 可见；只有 Bucket Manifest 引用的 `ObjectRecord` 才能做到。

### 为什么需要这个机制

只在内存保存 Part 会让重试和重启不可靠；直接写入对象历史又会暴露不完整值。独立持久命名空间既保存工作，又维持前面建立的单一发布边界。

### 运行时心智模型

服务分配确定性 upload ID，让 DiskStorage 创建 `uploads/<id>/upload.json` 和 `parts/`。`upload_part` 校验编号与上传身份，再原子写一个编号 `.data` 文件。Abort 只删除这次私有上传目录。

### 机制板块

<!-- journey-file: src/minis3/model.py -->
#### `src/minis3/model.py`

##### 是什么，为什么现在需要

Version 和 Marker 增加时间戳；数据版本还可记录完成它的 Multipart upload。

##### 在运行时做什么

后续生命周期和恢复会使用这些字段；它们仍是已发布历史上的不可变元数据。

##### 关键代码

```python
multipart_upload_id: str | None = None
```

##### 关键语句理解

`None` 表示普通 PUT；Multipart 完成版本可保留来源，但不会让上传过程本身变成可见历史。

<!-- journey-file: src/minis3/bucket.py -->
#### `src/minis3/bucket.py`

##### 是什么，为什么现在需要

Bucket PUT 接受可选的外部 ETag、时间戳与 Multipart 来源，同时保留普通 PUT 默认值。

##### 在运行时做什么

完成操作会复用同一版本迁移，而不是发明第二条发布路径。

##### 关键代码

```python
etag=content_etag(body) if etag is None else etag,
```

##### 关键语句理解

普通 PUT 仍计算 whole-body ETag；Multipart 完成可以传入验证后的组合 ETag。按组装 Body 重算会得到错误语义。

<!-- journey-file: src/minis3/storage/disk.py -->
#### `src/minis3/storage/disk.py`

##### 是什么，为什么现在需要

DiskStorage 增加私有上传布局、原子 Part 写入、身份校验、删除和重启恢复。

##### 在运行时做什么

它像管理对象 Artifact 一样管理持久 Staging，但普通 Manifest/List 从不读取 `uploads/`。

##### 关键代码

```python
atomic_write(directory / "parts" / f"{part.part_number:05d}.data", part.body)
```

##### 关键语句理解

Part 编号选择稳定文件名，`atomic_write` 完整替换它；重试不会留下半旧半新的字节。

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

公开服务增加 initiate、upload-part、abort 编排，以及可注入 clock 和最小 Part 大小。

##### 在运行时做什么

它在同一把锁下校验公开参数、分配确定性上传身份，再把私有字节委托给 DiskStorage。

##### 关键代码

```python
upload_id=f"u{sequence:08d}",
```

##### 关键语句理解

Upload ID 延续单调序列纪律，使重启恢复和学习追踪可复现，而不是依赖随机 UUID。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

Multipart 值与失败加入受支持包级 API。

##### 在运行时做什么

调用方可以持有 receipt 并捕获 `NoSuchUpload`，无需导入存储内部实现。

##### 关键语句理解

公开的是领域契约，不是私有磁盘布局。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/10-multipart-staging/tests.txt)`。它证明身份与范围拒绝，累计测试守住早期对象行为；完成可见性刻意留到下一阶段。

### 需要真正记住的内容

Staging 持久但私有；上传身份包含 Bucket 和 Key；同编号重试原子替换；只有 Bucket Manifest 发布才能创建对象。

### 用自己的话讲清楚

MiniS3 把未完成 Multipart 工作保存在独立持久命名空间。服务校验上传身份和 Part 编号，DiskStorage 原子替换编号 Part 文件；由于尚未发布 ObjectRecord，普通 GET/List 完全不受影响。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/06-multipart.md)
