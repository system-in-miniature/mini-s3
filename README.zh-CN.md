> **Language**: [English](README.md) | 简体中文

# MiniS3

[![CI](https://github.com/system-in-miniature/MiniS3/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/MiniS3/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniS3 是第八个**微型系统（System-in-Miniature）**教学项目：一个小型、
确定性的 S3 风格对象存储（S3-style object store），其重要机制都容纳在一个仓库中。
M1 聚焦于扁平对象键（flat object keys）、带引号的 MD5 ETag、存储桶版本控制
（bucket versioning）、删除标记（delete markers）、S3 风格的列表查询
（S3-style listing），以及在符合文档所述 POSIX rename/fsync 假设的文件系统上实现
本地崩溃一致的磁盘发布（locally crash-consistent disk publication）。

它刻意采用直接的 Python API，而不是 HTTP 服务器。运行时（runtime）仅使用
Python 标准库；pytest 是唯一的开发依赖。

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --dev
uv run pytest -q
uv run python labs/lab_versioning.py
uv run python labs/lab_directory_illusion.py
uv run python labs/lab_crash_atomicity.py
```

最小 API 用法：

```python
from minis3 import MiniS3

store = MiniS3("./minis3-data")
store.create_bucket("notes")
stored = store.put_object("notes", "team/plan.txt", b"ship M1")
assert store.get_object("notes", "team/plan.txt").body == b"ship M1"
print(stored.version_id, stored.etag)
```

`team/plan.txt` 是一个不透明的键。MiniS3 从不创建 `team/`；只有当
`list_objects(delimiter="/")` 对匹配的字符串进行分组时，才会出现看似目录的结果。

## M1 行为

- 未启用版本控制（unversioned）时，PUT 会替换唯一公开的 `null` 版本。
- 启用版本控制后，PUT 会创建 `v00000001` 这类确定性 ID。
- 启用版本控制后，DELETE 会添加一个删除标记并保留更早的字节内容。
- 按版本寻址（version-addressed）的 GET 和 DELETE 会对一个确切的保留条目执行操作。
- 暂停版本控制后，PUT 会替换 `null` 槽位，同时保留具名历史版本。
- 当前对象列表和版本列表具有强一致性（strong consistency）。
- 持久化写入会先 fsync 新建目录项和不可变产物，再通过一次原子清单重命名
  （atomic manifest rename）进行发布；启动恢复（startup recovery）会删除临时
  文件和未被引用的文件。

## 仓库导览

```text
src/minis3/
  model.py         immutable versions, markers, records, and ETags
  bucket.py        bucket versioning state machine
  listing.py       prefix, delimiter, pagination, and version projections
  store.py         public multi-bucket service API
  storage/         disk layout, atomic publication, and recovery
  multipart.py     M2 boundary (documentation only)
  conditional.py   M2 boundary (documentation only)
  lifecycle.py     M2 boundary (documentation only)
labs/              runnable mechanism demonstrations
tests/             behavior and crash-boundary contracts
docs/mapping.md    MiniS3 ↔ real S3 concept mapping
docs/DIFFERENCES.md explicit omissions and semantic differences
```

计划中的 M2 工作——分段上传、条件请求和生命周期——并未得到部分实现。请参阅
[docs/DIFFERENCES.md](docs/DIFFERENCES.md)。

## 商标声明

MiniS3 是独立的教学项目，与 Amazon.com, Inc. or its affiliates 无隶属、背书或赞助关系。"Amazon S3" 商标归其所有者所有。
