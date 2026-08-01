# Stage 03 · Durable storage boundary / 持久化存储边界

<!-- journey: chapter=5 tests_added=1 -->

## English

### Goal

Give Bucket state a durable representation with immutable artifacts and a publish-last manifest.

### Deliverable files

- `src/minis3/storage/__init__.py`
- `src/minis3/storage/atomic.py`
- `src/minis3/storage/disk.py`
- `tests/test_storage_boundary.py`

### The problem at this point

Stage 02 owns correct in-memory histories, but a process exit loses all of them. Writing one mutable JSON file directly is not enough: a crash can leave half a file or bytes whose directory entry was never made durable.

### Failure preview

The storage contract writes a bucket, creates a new `DiskStorage` over the same directory, and expects the exact body, ETag, version, and maximum sequence back. A missing fsync or publish order may pass an in-process read yet fail this restart observation.

### Test contract

<!-- journey-file: tests/test_storage_boundary.py -->
#### `tests/test_storage_boundary.py`

##### What it is and why it appears

This first storage contract proves one complete bucket can cross a process-like restart boundary.

##### Runtime role

It persists state, constructs a fresh adapter, and compares recovered values and sequence metadata. It is broader than a serialization unit test but narrower than the public MiniS3 service.

##### Key code

```python
recovered, maximum_sequence = DiskStorage(tmp_path).load_buckets()
```

##### Statement understanding

Using a new adapter is essential: reading the same in-memory Bucket would not prove bytes were published or recoverable. Returning `maximum` also prevents future sequence reuse.

### Basic concepts

Atomic visibility and durability are separate. `os.replace` makes readers observe either the old complete name or the new complete name. File `fsync` persists file bytes; parent-directory `fsync` persists the name change.

MiniS3 stores immutable data/metadata artifacts and a small mutable `manifest.json`. The manifest is the authority: only artifact IDs named by a successfully published manifest are visible after restart.

### Why this mechanism is necessary

Updating one large mutable state file makes every object write rewrite shared state and enlarges the crash surface. Immutable artifacts can be written safely first. Publishing their references last gives recovery one unambiguous commit record and lets it discard orphaned work.

### Runtime mental model

`DiskStorage.persist_bucket` writes every missing immutable artifact, then calls `atomic_write` for the manifest. `atomic_write` writes a temporary file, flushes and fsyncs it, replaces the final name, and fsyncs the parent. Startup loads only manifest references and cleans everything else.

### Mechanism blocks

<!-- journey-file: src/minis3/storage/atomic.py -->
#### `src/minis3/storage/atomic.py`

##### What it is and why it appears

This file owns reusable filesystem publication primitives rather than S3 domain decisions.

##### Runtime role

DiskStorage calls it whenever a file or directory entry must survive a crash. It is the lowest layer at which visibility and durability ordering can be inspected.

##### Key code

```python
os.replace(temporary, path)
fsync_directory(path.parent)
```

##### Statement understanding

Replace changes which complete file the final name refers to; the following directory fsync makes that rename durable. Reversing or omitting the second line can leave a rename visible now but absent after power loss.

<!-- journey-file: src/minis3/storage/disk.py -->
#### `src/minis3/storage/disk.py`

##### What it is and why it appears

This is the sole owner of disk layout, manifest publication, and restart recovery for buckets.

##### Runtime role

It translates Bucket histories into immutable `.data`/`.json` artifacts plus manifest references, and reconstructs Buckets on startup.

##### Key code

```python
self._inject("before_manifest_publish")
atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
self._inject("after_manifest_publish")
```

##### Statement understanding

The manifest write sits between two named crash points because it is the visibility boundary. Artifacts before it are harmless until referenced; after it, recovery must treat the new state as committed.

<!-- journey-file: src/minis3/storage/__init__.py -->
#### `src/minis3/storage/__init__.py`

##### What it is and why it appears

This package boundary exports the durable adapter and the deliberate crash type used by later recovery experiments.

##### Runtime role

It provides stable imports while keeping layout helpers internal.

##### Statement understanding

Exporting `DiskStorage` names the storage owner; exporting `InjectedCrash` makes crash boundaries testable without exposing every helper.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`. It proves a clean publish/restart path. Stages 07 and 08 will separately prove crash points and directory-fsync cleanup.

### Durable takeaways

Rename provides atomic visibility; fsync provides durability; the manifest is the commit record; immutable artifacts are not visible merely because they exist.

### Explain it in your own words

MiniS3 writes immutable object artifacts first and atomically publishes a manifest last. Recovery trusts that manifest, so a crash can leave extra files but cannot expose a half-published object. The rename is the visibility point and parent fsync makes that decision survive restart.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/05-crash-atomicity.md)

## 中文

### 目标

用不可变 Artifact 与最后发布的 Manifest 为 Bucket 状态建立持久表示。

### 交付文件

- `src/minis3/storage/__init__.py`
- `src/minis3/storage/atomic.py`
- `src/minis3/storage/disk.py`
- `tests/test_storage_boundary.py`

### 当前遇到的问题

Stage 02 已有正确内存历史，但进程退出就会全部消失。直接覆盖一个可变 JSON 也不够：崩溃可能留下半份文件，或者留下尚未持久化的目录项。

### 先看会坏在哪里

存储契约写入 Bucket 后，用同一目录创建全新的 `DiskStorage`，要求恢复完全相同的 Body、ETag、版本和最大序列。缺少 fsync 或发布顺序错误可能在进程内读取时看不出来，却会在这次重启观察中失败。

### 测试契约

<!-- journey-file: tests/test_storage_boundary.py -->
#### `tests/test_storage_boundary.py`

##### 是什么，为什么现在需要

这是第一条存储契约，证明一个完整 Bucket 能跨越类似进程重启的边界。

##### 在运行时做什么

它持久化状态、创建新适配器，再比较恢复后的值与序列元数据。它比序列化单测更广，但还没到公开 MiniS3 服务。

##### 关键代码

```python
recovered, maximum_sequence = DiskStorage(tmp_path).load_buckets()
```

##### 关键语句理解

必须使用新适配器；读取原内存 Bucket 无法证明字节已发布并可恢复。返回 `maximum` 还能避免未来复用序列。

### 基本概念

原子可见性与持久性不是一件事。`os.replace` 让读者看到旧完整文件或新完整文件；文件 `fsync` 持久化内容字节，父目录 `fsync` 持久化名称变化。

MiniS3 保存不可变数据/元数据 Artifact 与较小的可变 `manifest.json`。Manifest 是权威：重启后只有被成功发布 Manifest 引用的 Artifact 才可见。

### 为什么需要这个机制

直接更新一个大型可变状态文件会让每次对象写入都重写共享状态并扩大崩溃面。不可变 Artifact 可以先安全落盘，最后发布引用则给恢复过程一个明确提交记录，并允许清除孤儿数据。

### 运行时心智模型

`DiskStorage.persist_bucket` 先写缺失的不可变 Artifact，再为 Manifest 调用 `atomic_write`。后者写临时文件、flush、文件 fsync、替换最终名称、父目录 fsync。启动时只加载 Manifest 引用并清理其余内容。

### 机制板块

<!-- journey-file: src/minis3/storage/atomic.py -->
#### `src/minis3/storage/atomic.py`

##### 是什么，为什么现在需要

这个文件拥有可复用的文件系统发布原语，不负责 S3 领域决策。

##### 在运行时做什么

当文件或目录项必须跨崩溃保存时，DiskStorage 调用它；这里是检查可见性与持久化顺序的最底层边界。

##### 关键代码

```python
os.replace(temporary, path)
fsync_directory(path.parent)
```

##### 关键语句理解

replace 改变最终名称指向哪份完整文件，随后的目录 fsync 才持久化这次 rename。省略第二行可能出现“现在看得到，掉电后却消失”。

<!-- journey-file: src/minis3/storage/disk.py -->
#### `src/minis3/storage/disk.py`

##### 是什么，为什么现在需要

这是 Bucket 磁盘布局、Manifest 发布和启动恢复的唯一所有者。

##### 在运行时做什么

它把 Bucket 历史变成不可变 `.data`/`.json` Artifact 和 Manifest 引用，并在启动时重建 Bucket。

##### 关键代码

```python
self._inject("before_manifest_publish")
atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
self._inject("after_manifest_publish")
```

##### 关键语句理解

Manifest 写入被两个命名崩溃点夹住，因为它正是可见性边界。此前的 Artifact 尚未被引用；此后恢复必须把新状态视为已提交。

<!-- journey-file: src/minis3/storage/__init__.py -->
#### `src/minis3/storage/__init__.py`

##### 是什么，为什么现在需要

这个包边界导出持久适配器，以及后续崩溃实验使用的故意崩溃类型。

##### 在运行时做什么

它提供稳定导入，同时保持布局辅助函数为内部细节。

##### 关键语句理解

导出 `DiskStorage` 明确存储所有者；导出 `InjectedCrash` 让崩溃边界可测试，而不必公开全部 helper。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-durable-storage-boundary/tests.txt)`。它证明正常发布/重启路径；Stage 07、08 会分别证明崩溃点和目录 fsync 清理。

### 需要真正记住的内容

rename 提供原子可见性，fsync 提供持久性，Manifest 是提交记录；Artifact 存在不代表它已经可见。

### 用自己的话讲清楚

MiniS3 先写不可变对象 Artifact，最后原子发布 Manifest。恢复只信任 Manifest，所以崩溃可以留下多余文件，却不能暴露半发布对象。rename 是可见性点，父目录 fsync 让这个决定跨重启保存。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)
