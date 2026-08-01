> **Language**: [English](README.md) | 简体中文

# MiniS3

[![CI](https://github.com/system-in-miniature/mini-s3/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-s3/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniS3 是第八个**微型系统（System-in-Miniature）**教学项目：一个小型、
确定性的 S3 风格对象存储（S3-style object store），其重要机制都容纳在一个仓库中。
M2 覆盖扁平对象键、版本控制与删除标记、S3 风格列表查询、可持久恢复的
multipart complete 及其复合 ETag 陷阱、用于缓存/CAS 的 ETag 条件请求，以及由手动
时钟驱动的生命周期过期。在符合文档所述 POSIX rename/fsync 假设的文件系统上，
可见磁盘变更仍保持本地崩溃一致。

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
uv run python labs/lab_multipart_etag.py
uv run python labs/lab_conditional_cas.py
```

最小 API 用法：

```python
from minis3 import MiniS3

store = MiniS3("./minis3-data")
store.create_bucket("notes")
stored = store.put_object("notes", "team/plan.txt", b"ship M2")
assert store.get_object("notes", "team/plan.txt").body == b"ship M2"
print(stored.version_id, stored.etag)
```

`team/plan.txt` 是一个不透明的键。MiniS3 从不创建 `team/`；只有当
`list_objects(delimiter="/")` 对匹配的字符串进行分组时，才会出现看似目录的结果。

## M2 行为

- 未启用版本控制（unversioned）时，PUT 会替换唯一公开的 `null` 版本。
- 启用版本控制后，PUT 会创建 `v00000001` 这类确定性 ID。
- 启用版本控制后，DELETE 会添加一个删除标记并保留更早的字节内容。
- 按版本寻址（version-addressed）的 GET 和 DELETE 会对一个确切的保留条目执行操作。
- 暂停版本控制后，PUT 会替换 `null` 槽位，同时保留具名历史版本。
- 当前对象列表和版本列表具有强一致性（strong consistency）。
- 持久化写入会先 fsync 新建目录项和不可变产物，再通过一次原子清单重命名
  （atomic manifest rename）进行发布；启动恢复（startup recovery）会删除临时
  文件和未被引用的文件。
- Multipart 暂存可跨重启恢复，但不会进入对象列表；complete 校验有序 part 回执，
  再原子发布一个使用 S3 `md5(各 part MD5 二进制拼接)-N` ETag 的对象。
- GET 支持 `If-None-Match`（304 形态的 `NotModified`）和 `If-Match`；
  PUT/DELETE 在写锁内判定 `If-Match`，陈旧 ETag 得到 412 形态的
  `PreconditionFailed`。
- 纯 expiration 规则只在注入时间的显式 `lifecycle_tick` 中执行：当前版本化数据
  产生 delete marker，符合条件的 noncurrent 数据版本被物理删除。

## 三种学习模式

1. **[机制教程](docs/zh/tutorial/index.md)**：按主题理解对象存储机制。
2. **[自主重建](docs/zh/journey/index.md)**：通过 15 个完整浏览课程，依次理解当前
   问题、一条失败预览、基本概念、每个变更文件与关键语句。
3. **[Agent 带教](docs/zh/agent-guided.md)**：运行
   `python journey/tools/build_journey.py agent N`，在 Codex 中进入准备好的工作区，
   通过互动筛查、实现、小片段代码走读与 parity 验收完成 Stage N。

测试是可执行的问题动机和最终证据，不要求把整套课程写成测试优先。Agent 带教网页
只提供使用教程；实际教学行为由 `AGENTS.md` 和选中的 Stage 资料驱动。

## 仓库导览

```text
src/minis3/
  model.py         immutable versions, markers, records, and ETags
  bucket.py        bucket versioning state machine
  listing.py       prefix, delimiter, pagination, and version projections
  store.py         public multi-bucket service API
  storage/         disk layout, atomic publication, and recovery
  multipart.py     complete 清单校验与复合 ETag
  conditional.py   纯 If-Match / If-None-Match 判定
  lifecycle.py     纯 expiration 规则求值
labs/              runnable mechanism demonstrations
tests/             behavior and crash-boundary contracts
docs/mapping.md    MiniS3 ↔ real S3 concept mapping
docs/DIFFERENCES.md explicit omissions and semantic differences
```

每项 M2 机制的精确等价边界见 [docs/zh/mapping.md](docs/zh/mapping.md)；
本地实现和协议层简化仍明确记录在
[docs/zh/DIFFERENCES.md](docs/zh/DIFFERENCES.md)。

## 商标声明

MiniS3 是独立的教学项目，与 Amazon.com, Inc. or its affiliates 无隶属、背书或赞助关系。"Amazon S3" 商标归其所有者所有。
