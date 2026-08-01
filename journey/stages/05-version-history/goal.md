# Stage 05 · Version history projection / 版本历史投影

<!-- journey: chapter=3 tests_added=3 -->

## English

### Goal

Project complete histories without collapsing null versions, named versions, and delete markers.

### Deliverable files

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_versioning.py`

### The problem at this point

GET returns one addressed data version, so it cannot explain the history hidden behind the latest value or marker. Administrative and recovery views need every retained entry plus enough metadata to distinguish their meanings.

### Test contract

#### See the failure first

The suspended-delete contract creates named history, writes a `null` value, then deletes without a version ID. The expected history contains a new `null` marker and the older named versions, but not the replaced `null` data. A flat “all values” list would report the wrong state.

<!-- journey-file: tests/test_versioning.py -->
#### `tests/test_versioning.py`

##### What it is and why it appears

Three new scenarios lock the projection of unversioned replacement, suspended replacement, and suspended deletion.

##### Runtime role

They observe public histories after real service mutations, so the evidence covers Bucket plus projection rather than a fabricated input alone.

##### Key code

```python
assert marker is not None and marker.version_id == "null"
```

##### Statement understanding

Suspension does not mean deletion becomes physical. The new marker occupies the public `null` slot while named history remains addressable.

### Basic concepts

A projection is a read-only shape derived from owned state. `ListedVersion` does not become a second history owner; it converts each `Version` or `DeleteMarker` into fields useful to callers. `is_latest` depends on position within one key's newest-first tuple, not on the highest ID string globally.

### Why this mechanism is necessary

Returning raw internal objects would couple callers to storage fields and tempt them to mutate history. Returning only current data would erase markers and noncurrent versions. An explicit projection preserves semantics while keeping the aggregate authoritative.

### Runtime mental model

The service locks and passes Bucket records to `list_object_versions`. The pure function filters exact key prefixes, iterates keys deterministically, flattens each newest-first history, marks only index zero as latest, and returns an immutable result.

### Mechanism blocks

<!-- journey-file: src/minis3/listing.py -->
#### `src/minis3/listing.py`

##### What it is and why it appears

This read-side module introduces response values and the pure history projection.

##### Runtime role

It consumes records without mutation and emits a stable sequence carrying key, IDs, ETag/size when data exists, marker flag, and latest flag.

##### Key code

```python
etag=item.etag if is_data else None,
```

##### Statement understanding

A marker has no body-derived ETag. Making the field explicitly `None` preserves the distinction instead of inventing an empty-object fingerprint.

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

The public service gains a locked read method for the new projection.

##### Runtime role

It resolves the Bucket and delegates to the pure listing function while preventing a concurrent mutation from changing the snapshot mid-read.

##### Key code

```python
return list_object_versions(self._bucket(bucket).records, prefix=prefix)
```

##### Statement understanding

The service passes records but does not reproduce projection logic. This keeps ownership clear and makes the pure function independently understandable.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

The new result type becomes part of the supported package surface.

##### Runtime role

It lets callers name the response contract without importing an internal module path.

##### Statement understanding

Exporting a result value is a compatibility decision; the internal flattening helper remains an implementation detail.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`. The cumulative suite proves projection semantics across versioning states; current-object pagination belongs to Stage 06.

### Durable takeaways

A read projection explains state without owning it. Null data, named data, and markers remain distinct, and “latest” is local to each exact key history.

### Explain it in your own words

Version listing is a pure view over Bucket-owned history. It preserves entries that GET intentionally hides, marks the head of each key as latest, and keeps marker-only fields empty so callers can reconstruct what happened without mutating the source state.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/03-versioning.md)

## 中文

### 目标

投影完整历史，同时保持 null 版本、具名版本和删除标记可区分。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/listing.py`
- `src/minis3/store.py`
- `tests/test_versioning.py`

### 当前遇到的问题

GET 只返回一份被寻址的数据版本，无法解释最新值或 Marker 背后隐藏的历史。管理和恢复视图需要看到全部保留项，并有足够字段区分它们的含义。

### 测试契约

#### 先看会坏在哪里

暂停删除契约先创建具名历史，再写 `null` 值，最后不带版本 ID 删除。预期历史包含新的 `null` Marker 和旧具名版本，但不再包含被替换的 `null` 数据。简单“列出全部值”会报告错误状态。

<!-- journey-file: tests/test_versioning.py -->
#### `tests/test_versioning.py`

##### 是什么，为什么现在需要

三个新场景锁定未版本化替换、暂停替换和暂停删除后的投影。

##### 在运行时做什么

它们观察真实服务变更后的公开历史，因此证据同时覆盖 Bucket 与投影，而不是只测虚构输入。

##### 关键代码

```python
assert marker is not None and marker.version_id == "null"
```

##### 关键语句理解

暂停不表示删除变成物理删除。新 Marker 占据公开 `null` 槽，具名历史仍可寻址。

### 基本概念

投影是从已有状态派生的只读形状。`ListedVersion` 不成为第二个历史所有者；它只是把 `Version` 或 `DeleteMarker` 转成调用方需要的字段。`is_latest` 由单个 Key 的新到旧位置决定，不是全局比较 ID 字符串。

### 为什么需要这个机制

返回内部原始对象会把调用方耦合到存储字段并诱发修改；只返回当前数据又会抹掉 Marker 和非当前版本。显式投影既保留语义，也让聚合继续保持权威。

### 运行时心智模型

服务加锁，把 Bucket records 交给 `list_object_versions`。纯函数按精确 Key 前缀过滤、确定性遍历 Key、展开新到旧历史、只把索引 0 标成 latest，再返回不可变结果。

### 机制板块

<!-- journey-file: src/minis3/listing.py -->
#### `src/minis3/listing.py`

##### 是什么，为什么现在需要

这个读取侧模块引入响应值与纯历史投影。

##### 在运行时做什么

它不修改 records，只输出稳定序列，携带 Key、ID、数据存在时的 ETag/size、Marker 标记与 latest 标记。

##### 关键代码

```python
etag=item.etag if is_data else None,
```

##### 关键语句理解

Marker 没有基于 Body 的 ETag。显式使用 `None` 保留区别，而不是伪造一个空对象指纹。

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

公开服务增加带锁的历史读取方法。

##### 在运行时做什么

它解析 Bucket 并委托纯 Listing 函数，同时阻止并发变更在读取中途改变快照。

##### 关键代码

```python
return list_object_versions(self._bucket(bucket).records, prefix=prefix)
```

##### 关键语句理解

服务传入 records，但不重复投影逻辑。这样职责清晰，纯函数也能独立理解。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

新的结果类型成为受支持包级接口。

##### 在运行时做什么

调用方无需导入内部模块路径就能引用响应契约。

##### 关键语句理解

导出结果值是兼容性决策；内部展开 helper 仍是实现细节。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/05-version-history/tests.txt)`。累计测试证明跨版本状态的投影语义；当前对象分页属于 Stage 06。

### 需要真正记住的内容

读取投影解释状态但不拥有状态。null 数据、具名数据、Marker 保持可区分，“latest” 只属于单个精确 Key 历史。

### 用自己的话讲清楚

版本 Listing 是 Bucket 历史的纯视图。它保留 GET 故意隐藏的条目，把每个 Key 的历史头标为 latest，并让 Marker 的数据字段保持为空，使调用方能还原发生了什么而不修改源状态。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/03-versioning.md)
