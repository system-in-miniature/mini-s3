# Stage 01 · Scaffold and object values / 脚手架与对象值

<!-- journey: chapter=1 tests_added=3 -->

## English

### Goal

Create an installable package and the immutable values that every later object operation will carry.

### Deliverable files

- `README.md`
- `pyproject.toml`
- `src/minis3/__init__.py`
- `src/minis3/errors.py`
- `src/minis3/model.py`
- `tests/test_model.py`
- `uv.lock`

### The problem at this point

The journey starts with no package and no vocabulary for an object. Before implementing PUT or GET, MiniS3 needs exact answers to four questions: what bytes make up a value, how that value is identified, how one version differs from a deletion, and whether a key such as `photos/2026/a.jpg` is a path or just a string.

This stage creates those values without adding storage or service behavior. Later stages can change histories and persistence while continuing to pass the same immutable objects between boundaries.

### Failure preview

The highest-signal contract uses `ObjectRecord(key="/a//b/")` and expects the exact same string back. If model code treats the key as a filesystem path, repeated or leading slashes may disappear before storage even exists. The test makes that corruption visible at the smallest possible boundary.

### Basic concepts

An S3 object value is a complete byte string, not an editable file range. A normal ETag in this miniature is the quoted lowercase MD5 of those bytes. It is a content fingerprint used for comparison; it is not an access-control secret.

A key is opaque. Slashes can be used by listing code to present a directory-like view later, but the model must preserve every character exactly. A `Version` carries bytes; a `DeleteMarker` carries identity and ordering only, because it hides older data rather than storing an empty object.

### Why this mechanism is necessary

If these meanings were left as loose dictionaries, later code could mutate a historical version, normalize a key, or accidentally attach bytes to a delete marker. That would make versioning and recovery ambiguous. Frozen value objects make invalid state harder to create and give every later layer one shared vocabulary.

### Runtime mental model

At this stage the flow is deliberately short: caller bytes enter `content_etag`, become an ETag, and are placed in a `Version`; an `ObjectRecord` associates an exact key with a newest-first tuple of versions. No class here owns I/O or mutation. It only defines values that Bucket, storage, and service code will own later.

### Mechanism blocks

<!-- journey-file: src/minis3/errors.py -->
#### `src/minis3/errors.py`

##### What it is and why it appears

This file defines protocol-independent domain failures. Bucket and service code can raise a precise error without importing HTTP concepts.

##### Runtime role

Callers catch subclasses of `MiniS3Error` and may later translate them to S3-shaped responses. Keeping missing bucket, missing key, and missing version distinct prevents one broad exception from erasing useful semantics.

##### Key code

```python
class NoSuchKey(MiniS3Error):
```

##### Statement understanding

Inheritance says this is part of MiniS3's public failure vocabulary while remaining distinguishable from `NoSuchBucket` and `NoSuchVersion`.

<!-- journey-file: src/minis3/model.py -->
#### `src/minis3/model.py`

##### What it is and why it appears

This is the stage's central domain-value file. It defines whole-object versions, body-less delete markers, per-key history, and content-derived ETags.

##### Runtime role

Later Bucket code constructs these values, listing code projects them, and disk storage serializes them. The values themselves perform no I/O and own no global state.

##### Key code

```python
digest = md5(body, usedforsecurity=False).hexdigest()
return f'"{digest}"'
```

##### Statement understanding

`usedforsecurity=False` documents that MD5 is used as the S3-style fingerprint, not as a security primitive. Quoting the hexadecimal digest is part of the externally visible ETag representation, so returning the bare digest would be a semantic bug.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

This package boundary exposes the names a learner or later service can import from `minis3` without knowing the internal module layout.

##### Runtime role

It performs wiring only. If a public name is missing here, import fails before any object flow begins; it does not own ETag or version behavior.

##### Statement understanding

The explicit imports are the first public API contract. Internal helpers stay internal until a later stage deliberately exports them.

<!-- journey-file: tests/test_model.py -->
#### `tests/test_model.py`

##### What it is and why it appears

These tests record the three model invariants introduced today: quoted ETags, opaque keys with immutable values, and body-less delete markers.

##### Runtime role

They call the learner-visible values directly. They prove value semantics only; they do not yet prove bucket transitions, disk persistence, or a public object service.

##### Key code

```python
assert record.key == "/a//b/"
```

##### Statement understanding

The deliberately unusual key catches path normalization. Passing this assertion means the model preserved the exact string, not that directory behavior exists.

<!-- journey-file: README.md -->
#### `README.md`

##### What it is and why it appears

This is the small learner-workspace entry point. It states that the repository is rebuilt in verified stages.

##### Runtime role

It has no runtime responsibility; it helps a learner recognize that this checkout is a staged reconstruction rather than the finished repository.

##### Statement understanding

The wording “one verified stage at a time” defines the workspace workflow, not an object-storage invariant.

<!-- journey-file: pyproject.toml -->
#### `pyproject.toml`

##### What it is and why it appears

This file makes `src/minis3` installable and tells pytest where source and tests live.

##### Runtime role

Build and test tools read it before Python imports MiniS3. A wrong package path looks like an import failure even when the model code itself is correct.

##### Statement understanding

`packages = ["src/minis3"]` connects the src-layout directory to the built package; `testpaths = ["tests"]` keeps test discovery bounded.

<!-- journey-file: uv.lock -->
#### `uv.lock`

##### What it is and why it appears

The lockfile records the exact development dependency graph used to run this stage.

##### Runtime role

It affects environment reproduction, not object behavior. It should be debugged when dependency resolution differs between machines.

##### Statement understanding

The editable `minis3` entry connects the local package to the locked environment, while the pytest version is resolved reproducibly.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/01-scaffold-object-model/tests.txt)`. The three tests prove the three value invariants above. They do not prove storage, version transitions, or service behavior because none exists yet.

### Durable takeaways

Keep four facts together: an object is whole bytes, its normal ETag is a quoted content fingerprint, its key is an opaque exact string, and a delete marker is not an empty object.

### Explain it in your own words

MiniS3 first establishes immutable object values so later state machines and storage code cannot disagree about what a key, data version, ETag, or deletion means. The important constraint is that slashes remain data and markers never carry a body; violating either rule corrupts later listing or version history.

### Textbook

[Chapter 1](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/01-getting-started.md)

## 中文

### 目标

建立可安装的 Python 包，以及后续所有对象操作都会传递的不可变领域值。

### 交付文件

- `README.md`
- `pyproject.toml`
- `src/minis3/__init__.py`
- `src/minis3/errors.py`
- `src/minis3/model.py`
- `tests/test_model.py`
- `uv.lock`

### 当前遇到的问题

旅程开始时既没有包，也没有“对象”的准确词汇。在实现 PUT/GET 以前，MiniS3 必须先回答四件事：对象值由哪些字节组成、如何标识这份值、普通版本与删除有什么区别，以及 `photos/2026/a.jpg` 这样的 Key 究竟是路径还是普通字符串。

本阶段只建立这些值，不引入存储和服务行为。后续阶段可以增加历史与持久化，同时继续在边界之间传递同一套不可变对象。

### 先看会坏在哪里

最直观的契约会创建 `ObjectRecord(key="/a//b/")`，并要求读取时得到完全相同的字符串。如果模型把 Key 当文件系统路径，开头或重复斜杠可能在存储出现以前就被吞掉。这个测试在最小边界上直接暴露数据被改写的问题。

### 基本概念

S3 对象值是一整段字节，不是可局部编辑的文件。本项目里的普通 ETag 是对象字节的带引号小写 MD5；它用于比较内容，不是访问控制密钥。

Key 是不透明字符串。后面的 Listing 可以利用斜杠展示类似目录的结果，但模型必须逐字符保留 Key。`Version` 携带 Body；`DeleteMarker` 只携带身份和顺序，因为它的作用是遮蔽旧数据，而不是保存一个空对象。

### 为什么需要这个机制

如果用松散字典表达这些含义，后续代码可能修改历史版本、规范化 Key，或者误给删除标记附加 Body，版本化和恢复就会变得含糊。冻结的领域值限制了非法状态，也让 Bucket、存储和服务共享同一种语言。

### 运行时心智模型

当前流程很短：调用方的 bytes 进入 `content_etag` 得到 ETag，再进入 `Version`；`ObjectRecord` 把精确 Key 与按新到旧排列的版本元组关联起来。这里没有任何类负责 I/O 或全局变更，它们只是后续边界要使用的值。

### 机制板块

<!-- journey-file: src/minis3/errors.py -->
#### `src/minis3/errors.py`

##### 是什么，为什么现在需要

这里定义与 HTTP 无关的领域错误。Bucket 和服务代码可以准确表达失败，而不依赖传输协议。

##### 在运行时做什么

调用方可以捕获 `MiniS3Error` 的具体子类，再映射成协议响应。缺 Bucket、缺 Key、缺具体版本必须分开，否则会丢失语义。

##### 关键代码

```python
class NoSuchKey(MiniS3Error):
```

##### 关键语句理解

继承关系表示它属于 MiniS3 的公开失败词汇，同时仍可与 `NoSuchBucket`、`NoSuchVersion` 区分。

<!-- journey-file: src/minis3/model.py -->
#### `src/minis3/model.py`

##### 是什么，为什么现在需要

这是本阶段的核心领域值文件，定义完整对象版本、无 Body 删除标记、Key 的历史和内容 ETag。

##### 在运行时做什么

后续 Bucket 构造这些值，Listing 投影它们，磁盘层序列化它们；这些值自身不执行 I/O，也不拥有全局状态。

##### 关键代码

```python
digest = md5(body, usedforsecurity=False).hexdigest()
return f'"{digest}"'
```

##### 关键语句理解

`usedforsecurity=False` 明确 MD5 在这里是 S3 风格指纹，不是安全算法。外层引号属于 ETag 的公开表示，返回裸摘要会造成语义错误。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

这是包级公开边界，让学习者和后续服务可以从 `minis3` 导入稳定名称，而不必知道内部模块布局。

##### 在运行时做什么

它只负责接线。名称漏导出会在对象流程开始前表现为 import 失败，但它不拥有 ETag 或版本行为。

##### 关键语句理解

显式导入组成第一版公开 API；内部辅助函数只有在后续阶段明确加入时才成为公开能力。

<!-- journey-file: tests/test_model.py -->
#### `tests/test_model.py`

##### 是什么，为什么现在需要

三个测试分别固定带引号 ETag、含斜杠的不透明 Key 与不可变性、无 Body 删除标记。

##### 在运行时做什么

它们直接调用学习者可见的领域值，只证明值语义；目前还不能证明 Bucket 迁移、磁盘持久化或对象服务。

##### 关键代码

```python
assert record.key == "/a//b/"
```

##### 关键语句理解

故意使用异常形状的 Key 是为了捕获路径规范化。断言通过只证明字符串被原样保存，不代表系统真的存在目录。

<!-- journey-file: README.md -->
#### `README.md`

##### 是什么，为什么现在需要

这是学习工作区的短入口，说明仓库会按可验证 Stage 重建。

##### 在运行时做什么

它不参与运行时，只帮助学习者识别这是阶段式重建工作区，而不是完成品源码。

##### 关键语句理解

“one verified stage at a time” 描述学习流程，不是对象存储不变量。

<!-- journey-file: pyproject.toml -->
#### `pyproject.toml`

##### 是什么，为什么现在需要

它让 `src/minis3` 可安装，并告诉 pytest 源码与测试的位置。

##### 在运行时做什么

构建与测试工具先读取它，再导入 MiniS3。包路径配置错误时，即使模型代码正确也会表现为 import 失败。

##### 关键语句理解

`packages = ["src/minis3"]` 把 src-layout 目录接到构建产物；`testpaths = ["tests"]` 限定测试发现范围。

<!-- journey-file: uv.lock -->
#### `uv.lock`

##### 是什么，为什么现在需要

锁文件记录运行本阶段时的精确开发依赖图。

##### 在运行时做什么

它影响环境复现，不影响对象语义；不同机器解析出不同依赖时再从这里排查。

##### 关键语句理解

editable 的 `minis3` 条目把本地包接入锁定环境，pytest 版本也因此可复现。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/01-scaffold-object-model/tests.txt)`。三个测试分别证明上述三个值不变量；它们不证明尚不存在的存储、版本迁移或服务行为。

### 需要真正记住的内容

把四件事连起来：对象是完整字节；普通 ETag 是带引号内容指纹；Key 是精确的不透明字符串；删除标记不是空对象。

### 用自己的话讲清楚

MiniS3 先建立不可变对象值，避免后续状态机和存储层对 Key、数据版本、ETag 与删除产生不同理解。关键约束是斜杠仍属于数据、Marker 永远没有 Body；破坏任一约束都会污染后续 Listing 或版本历史。

### 教材

[第 1 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/01-getting-started.md)
