# MiniS3 Tutorial / MiniS3 教程

[Chinese edition / 中文版](zh/index.md)

MiniS3 is a deterministic Python teaching implementation of core S3-style
object-storage mechanisms: flat keys, versioning, listing, multipart composite
ETags, conditional CAS, manually ticked lifecycle expiration, and
crash-consistent local publication. It exposes a direct Python API rather than
an HTTP/S3-compatible server.

MiniS3 是一个确定性的 Python 教学实现，覆盖 S3 风格对象存储的核心机制：
扁平键、版本控制、列表查询、multipart 复合 ETag、条件 CAS、手动 tick 的
lifecycle expiration，以及崩溃一致的本地发布。它提供直接 Python API，而不是
兼容 HTTP/S3 的服务器。

## Install / 安装

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/system-in-miniature/mini-s3.git
cd mini-s3
uv sync --dev
```

## First experiment / 第一个实验

```bash
uv run python labs/lab_versioning.py
```

The script writes two versions, creates a delete marker, shows that an ordinary
GET now raises `NoSuchKey`, and then retrieves the retained first version by
its version ID.

脚本写入两个版本、创建删除标记，展示普通 GET 此时得到 `NoSuchKey`，然后按
version ID 取回仍被保留的第一个版本。

## Choose a learning mode / 选择学习模式

### Mechanism Tutorial / 机制教程

Read the [Mechanism Tutorial](tutorial/index.md) when you want a topic-oriented
explanation of object values, versioning, listing, crash atomicity, multipart,
conditional requests, and lifecycle expiration.

如果你希望按主题系统理解对象值、版本化、Listing、崩溃原子性、Multipart、条件请求
与生命周期，请阅读[机制教程](zh/tutorial/index.md)。

### Self-Guided Rebuild / 自主重建

Follow the [Self-Guided Rebuild](journey/index.md) to learn through 15 cumulative
browser lessons. Each Stage explains the problem and failure first, then walks
through every changed file and its critical statements.

通过[自主重建](zh/journey/index.md)完成 15 个累积浏览课程。每个 Stage 先解释问题与
失败场景，再逐文件理解关键语句。

### Agent-Guided Rebuild / Agent 带教

Use the [Agent-Guided Rebuild tutorial](agent-guided.md) to prepare `stage-NN`
in a dedicated workspace and learn interactively with Codex through `AGENTS.md`.

按照 [Agent 带教使用教程](zh/agent-guided.md)准备专用工作区中的 `stage-NN`，再由
Codex 根据 `AGENTS.md` 进行互动带教。

## Reading path / 阅读顺序

Use the repository tour for the code layout, then read the concept mapping.
Run all five labs before reading the differences chapter so that a successful
local experiment is not mistaken for Amazon S3 compatibility.

先通过仓库导览理解代码布局，再读概念映射。运行五个 lab 后再读差异章节，
避免把本地实验成功误解成 Amazon S3 兼容性证据。

The [English README](https://github.com/system-in-miniature/mini-s3#readme)
contains the complete M2 scope and minimal API example. The
[design history archive](superpowers/README.md) reflects construction-time
plans; canonical docs and tests define current behavior.

完整 M2 范围与最小 API 示例见
[中文 README](https://github.com/system-in-miniature/mini-s3/blob/main/README.zh-CN.md)。
[设计历史存档](superpowers/README.md)反映建设期计划；正典文档与测试定义当前行为。
