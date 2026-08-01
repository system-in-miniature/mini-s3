# Stage 01 · 脚手架与对象值

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

### 机制走读

#### 所有权与数据流

`model.py` 拥有不可变完整对象值：字节进入 `content_etag` 形成带引号指纹，再随 `Version` 进入 `ObjectRecord`；`DeleteMarker` 只遮蔽历史，不携带 Body。

#### 失败与排查

从值构造器与 ETag 断言开始排查。`key` 中的斜杠必须原样保留，对象必须不可变，删除标记不能意外获得对象字节。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `src/minis3/errors.py`

共享的领域失败词汇。

由 Bucket/服务代码构造并向上返回，不拥有 I/O；状态正确但结果异常时检查这些字段。

**变化锚点:** `MiniS3Error`, `BucketAlreadyExists`, `NoSuchBucket`, `BucketNotEmpty`, `NoSuchKey`, `NoSuchVersion`, `InvalidContinuationToken`

??? note "文件差异：src/minis3/errors.py"
    ```diff
    diff --git a/src/minis3/errors.py b/src/minis3/errors.py
    new file mode 100644
    index 0000000..e1a2230
    --- /dev/null
    +++ b/src/minis3/errors.py
    @@ -0,0 +1,30 @@
    +"""Public, S3-shaped domain errors without an HTTP dependency."""
    +
    +
    +class MiniS3Error(Exception):
    +    """Base class for errors callers may translate to protocol responses."""
    +
    +
    +class BucketAlreadyExists(MiniS3Error):
    +    """The requested bucket name is already present."""
    +
    +
    +class NoSuchBucket(MiniS3Error):
    +    """The requested bucket does not exist."""
    +
    +
    +class BucketNotEmpty(MiniS3Error):
    +    """A bucket with live records or retained versions cannot be deleted."""
    +
    +
    +class NoSuchKey(MiniS3Error):
    +    """The current key is absent or hidden by a delete marker (HTTP 404)."""
    +
    +
    +class NoSuchVersion(MiniS3Error):
    +    """The requested version id is not retained for this key."""
    +
    +
    +class InvalidContinuationToken(MiniS3Error):
    +    """The list continuation token was malformed or belongs to another query."""
    +
    ```

#### `src/minis3/model.py`

贯穿系统的不可变领域值。

由 Bucket/服务代码构造并向上返回，不拥有 I/O；状态正确但结果异常时检查这些字段。

**变化锚点:** `content_etag`, `Version`, `size`, `is_delete_marker`, `DeleteMarker`, `ObjectRecord`

??? note "文件差异：src/minis3/model.py"
    ```diff
    diff --git a/src/minis3/model.py b/src/minis3/model.py
    new file mode 100644
    index 0000000..da662fc
    --- /dev/null
    +++ b/src/minis3/model.py
    @@ -0,0 +1,75 @@
    +"""Immutable values for a flat object namespace.
    +
    +S3 keys are opaque strings. A slash has no storage meaning: ``a/b`` is not a
    +file named ``b`` inside directory ``a``. Directory-like views are computed by
    +``list_objects`` from its ``prefix`` and ``delimiter`` arguments.
    +
    +An object record is an ordered history. Data versions carry a complete byte
    +body because PUT replaces an object as a whole; delete markers carry no body.
    +"""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from hashlib import md5
    +from typing import TypeAlias
    +
    +
    +NULL_VERSION_ID = "null"
    +
    +
    +def content_etag(body: bytes) -> str:
    +    """Return S3's quoted hexadecimal MD5 ETag for a non-multipart body."""
    +
    +    # usedforsecurity=False documents that MD5 is an object fingerprint here,
    +    # not an authentication or collision-resistance primitive.
    +    digest = md5(body, usedforsecurity=False).hexdigest()
    +    return f'"{digest}"'
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Version:
    +    """One immutable, complete value of an object."""
    +
    +    version_id: str
    +    storage_id: str
    +    sequence: int
    +    body: bytes
    +    etag: str
    +
    +    @property
    +    def size(self) -> int:
    +        """Number of bytes in the complete object value."""
    +
    +        return len(self.body)
    +
    +    @property
    +    def is_delete_marker(self) -> bool:
    +        """Allow data versions and markers to share listing code."""
    +
    +        return False
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class DeleteMarker:
    +    """A version whose presence hides older data without deleting it."""
    +
    +    version_id: str
    +    storage_id: str
    +    sequence: int
    +
    +    @property
    +    def is_delete_marker(self) -> bool:
    +        return True
    +
    +
    +ObjectVersion: TypeAlias = Version | DeleteMarker
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ObjectRecord:
    +    """All versions for one exact key, newest first."""
    +
    +    key: str
    +    versions: tuple[ObjectVersion, ...] = ()
    +
    ```

#### `src/minis3/__init__.py`

受支持的包级公开接口。

由用户导入触达；接线错误会在运行时流程开始前表现为名称缺失。

**变化锚点:** 配置、导出或文档变化

??? note "文件差异：src/minis3/__init__.py"
    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    new file mode 100644
    index 0000000..8a3d1c7
    --- /dev/null
    +++ b/src/minis3/__init__.py
    @@ -0,0 +1,3 @@
    +"""Public API for the MiniS3 teaching implementation."""
    +from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
    +from .model import DeleteMarker, ObjectRecord, Version, content_etag
    ```

#### `tests/test_model.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `test_etag_is_quoted_lowercase_content_md5`, `test_keys_are_opaque_even_when_they_contain_slashes`, `test_delete_marker_has_no_object_body`

??? note "文件差异：tests/test_model.py"
    ```diff
    diff --git a/tests/test_model.py b/tests/test_model.py
    new file mode 100644
    index 0000000..01151ba
    --- /dev/null
    +++ b/tests/test_model.py
    @@ -0,0 +1,35 @@
    +"""Executable contracts for MiniS3's flat object model."""
    +
    +from dataclasses import FrozenInstanceError
    +
    +import pytest
    +
    +from minis3 import DeleteMarker, ObjectRecord, Version, content_etag
    +
    +
    +def test_etag_is_quoted_lowercase_content_md5() -> None:
    +    assert content_etag(b"hello") == '"5d41402abc4b2a76b9719d911017c592"'
    +
    +
    +def test_keys_are_opaque_even_when_they_contain_slashes() -> None:
    +    version = Version(
    +        version_id="null",
    +        storage_id="e00000001",
    +        sequence=1,
    +        body=b"x",
    +        etag=content_etag(b"x"),
    +    )
    +    record = ObjectRecord(key="/a//b/", versions=(version,))
    +
    +    assert record.key == "/a//b/"
    +    assert record.versions == (version,)
    +    with pytest.raises(FrozenInstanceError):
    +        version.etag = "changed"  # type: ignore[misc]
    +
    +
    +def test_delete_marker_has_no_object_body() -> None:
    +    marker = DeleteMarker(
    +        version_id="v00000002", storage_id="e00000002", sequence=2
    +    )
    +    assert marker.is_delete_marker is True
    +
    ```

#### `README.md`

Journey 工作区入口说明。

支撑安装或入口说明，不属于运行时数据流；导入、构建或命令执行前失败时从这里排查。

**变化锚点:** 配置、导出或文档变化

??? note "文件差异：README.md"
    ```diff
    diff --git a/README.md b/README.md
    new file mode 100644
    index 0000000..27585a5
    --- /dev/null
    +++ b/README.md
    @@ -0,0 +1,3 @@
    +# MiniS3 Journey workspace
    +
    +Build the object store one verified stage at a time.
    ```

#### `pyproject.toml`

安装与测试配置。

支撑安装或入口说明，不属于运行时数据流；导入、构建或命令执行前失败时从这里排查。

**变化锚点:** 配置、导出或文档变化

??? note "文件差异：pyproject.toml"
    ```diff
    diff --git a/pyproject.toml b/pyproject.toml
    new file mode 100644
    index 0000000..9167f50
    --- /dev/null
    +++ b/pyproject.toml
    @@ -0,0 +1,24 @@
    +[build-system]
    +requires = ["hatchling"]
    +build-backend = "hatchling.build"
    +
    +[project]
    +name = "minis3"
    +version = "0.1.0"
    +description = "A deterministic S3 system-in-miniature for teaching"
    +readme = "README.md"
    +requires-python = ">=3.12"
    +dependencies = []
    +
    +[dependency-groups]
    +dev = [
    +    "pytest>=9,<10",
    +]
    +
    +[tool.hatch.build.targets.wheel]
    +packages = ["src/minis3"]
    +
    +[tool.pytest.ini_options]
    +pythonpath = ["src", "."]
    +testpaths = ["tests"]
    +
    ```

#### `uv.lock`

可复现依赖锁。

支撑安装或入口说明，不属于运行时数据流；导入、构建或命令执行前失败时从这里排查。

**变化锚点:** 配置、导出或文档变化

??? note "文件差异：uv.lock"
    ```diff
    diff --git a/uv.lock b/uv.lock
    new file mode 100644
    index 0000000..90ad0d9
    --- /dev/null
    +++ b/uv.lock
    @@ -0,0 +1,79 @@
    +version = 1
    +revision = 3
    +requires-python = ">=3.12"
    +
    +[[package]]
    +name = "colorama"
    +version = "0.4.6"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz", hash = "sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44", size = 27697, upload-time = "2022-10-25T02:36:22.414Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/d1/d6/3965ed04c63042e047cb6a3e6ed1a63a35087b6a609aa3a15ed8ac56c221/colorama-0.4.6-py2.py3-none-any.whl", hash = "sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6", size = 25335, upload-time = "2022-10-25T02:36:20.889Z" },
    +]
    +
    +[[package]]
    +name = "iniconfig"
    +version = "2.3.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/72/34/14ca021ce8e5dfedc35312d08ba8bf51fdd999c576889fc2c24cb97f4f10/iniconfig-2.3.0.tar.gz", hash = "sha256:c76315c77db068650d49c5b56314774a7804df16fee4402c1f19d6d15d8c4730", size = 20503, upload-time = "2025-10-18T21:55:43.219Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl", hash = "sha256:f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12", size = 7484, upload-time = "2025-10-18T21:55:41.639Z" },
    +]
    +
    +[[package]]
    +name = "minis3"
    +version = "0.1.0"
    +source = { editable = "." }
    +
    +[package.dev-dependencies]
    +dev = [
    +    { name = "pytest" },
    +]
    +
    +[package.metadata]
    +
    +[package.metadata.requires-dev]
    +dev = [{ name = "pytest", specifier = ">=9,<10" }]
    +
    +[[package]]
    +name = "packaging"
    +version = "26.2"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/d7/f1/e7a6dd94a8d4a5626c03e4e99c87f241ba9e350cd9e6d75123f992427270/packaging-26.2.tar.gz", hash = "sha256:ff452ff5a3e828ce110190feff1178bb1f2ea2281fa2075aadb987c2fb221661", size = 228134, upload-time = "2026-04-24T20:15:23.917Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/df/b2/87e62e8c3e2f4b32e5fe99e0b86d576da1312593b39f47d8ceef365e95ed/packaging-26.2-py3-none-any.whl", hash = "sha256:5fc45236b9446107ff2415ce77c807cee2862cb6fac22b8a73826d0693b0980e", size = 100195, upload-time = "2026-04-24T20:15:22.081Z" },
    +]
    +
    +[[package]]
    +name = "pluggy"
    +version = "1.6.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz", hash = "sha256:7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3", size = 69412, upload-time = "2025-05-15T12:30:07.975Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl", hash = "sha256:e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746", size = 20538, upload-time = "2025-05-15T12:30:06.134Z" },
    +]
    +
    +[[package]]
    +name = "pygments"
    +version = "2.20.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz", hash = "sha256:6757cd03768053ff99f3039c1a36d6c0aa0b263438fcab17520b30a303a82b5f", size = 4955991, upload-time = "2026-03-29T13:29:33.898Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/f4/7e/a72dd26f3b0f4f2bf1dd8923c85f7ceb43172af56d63c7383eb62b332364/pygments-2.20.0-py3-none-any.whl", hash = "sha256:81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176", size = 1231151, upload-time = "2026-03-29T13:29:30.038Z" },
    +]
    +
    +[[package]]
    +name = "pytest"
    +version = "9.1.1"
    +source = { registry = "https://pypi.org/simple" }
    +dependencies = [
    +    { name = "colorama", marker = "sys_platform == 'win32'" },
    +    { name = "iniconfig" },
    +    { name = "packaging" },
    +    { name = "pluggy" },
    +    { name = "pygments" },
    +]
    +sdist = { url = "https://files.pythonhosted.org/packages/e4/47/b9efed96c114afcfa3c9d3fe98a76a1d14c74a9e266d397cf6eb64be5e01/pytest-9.1.1.tar.gz", hash = "sha256:1088fbde8f2b49d95a549a195707afa7a76a3ce9bcadc26b6d71f0ffda5fe313", size = 1636369, upload-time = "2026-06-19T10:58:32.857Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl", hash = "sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c", size = 386536, upload-time = "2026-06-19T10:58:31.347Z" },
    +]
    ```

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

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/tree/stage-01)

完成后可运行 `git checkout stage-01` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/01-scaffold-object-model/stage.patch)
