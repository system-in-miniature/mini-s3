# Stage 01 · Scaffold and object values / 脚手架与对象值

<!-- journey: chapter=1 tests_added=3 -->

## English

### Goal

Create an installable package and immutable values for bytes, ETags, opaque keys, and delete markers.

### Hands-on task

Starting from an empty tree, Implement `content_etag(body: bytes) -> str`, `Version`, `DeleteMarker`, and `ObjectRecord`. Keep all behavior inside the listed source-like boundaries; do not copy the patch first.

### Deliverable files / 交付文件

- `README.md`
- `pyproject.toml`
- `src/minis3/__init__.py`
- `src/minis3/errors.py`
- `src/minis3/model.py`
- `tests/test_model.py`
- `uv.lock`

### Self-check

1. Where is this stage's visibility or state transition owned?

    ??? note "Answer"
        S3 stores whole object values; a slash in a key is data, not a directory.

2. Which test would fail first if the new boundary were bypassed?

    ??? note "Answer"
        Read `tests.txt`, identify the narrowest new node, and name the public call it exercises.

### Pass command

`uv run pytest -q $(cat journey/stages/01-scaffold-object-model/tests.txt)`

### The real S3 lesson

S3 stores whole object values; a slash in a key is data, not a directory.

### Textbook

[Chapter 1](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/01-getting-started.md)

## 中文

### 目标

建立可安装包，以及表示字节、ETag、不透明 Key 和删除标记的不可变值。

### 动手任务

从空目录开始，实现 `content_etag(body: bytes) -> str`、`Version`、`DeleteMarker` 与 `ObjectRecord`。 行为必须留在下列源码同构边界中；不要先复制补丁。

### 交付文件

- `README.md`
- `pyproject.toml`
- `src/minis3/__init__.py`
- `src/minis3/errors.py`
- `src/minis3/model.py`
- `tests/test_model.py`
- `uv.lock`

### 自查

1. 本阶段的可见性或状态迁移由谁负责？

    ??? note "答案"
        S3 保存完整对象值；Key 中的斜杠只是数据，不是目录。

2. 如果绕过新边界，哪个测试会最先失败？

    ??? note "答案"
        阅读 `tests.txt`，找出最窄的新节点，并说出它覆盖的公开调用。

### 通关命令

`uv run pytest -q $(cat journey/stages/01-scaffold-object-model/tests.txt)`

### 对应真实 S3 的一课

S3 保存完整对象值；Key 中的斜杠只是数据，不是目录。

### 教材

[第 1 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/01-getting-started.md)
