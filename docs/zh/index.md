# MiniS3 教程

[English](../index.md)

MiniS3 是一个确定性的 Python 教学实现，覆盖 S3 风格对象存储的核心机制：
扁平键、版本控制、列表查询、multipart 复合 ETag、条件 CAS、手动 tick 的
lifecycle expiration，以及崩溃一致的本地发布。它提供直接 Python API，而不是
兼容 HTTP/S3 的服务器。

## 安装

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/system-in-miniature/mini-s3.git
cd mini-s3
uv sync --dev
```

## 第一个实验

```bash
uv run python labs/lab_versioning.py
```

脚本写入两个版本、创建删除标记，展示普通 GET 此时得到 `NoSuchKey`，然后按
version ID 取回仍被保留的第一个版本。

## 阅读顺序

先通过仓库导览理解代码布局，再读概念映射。运行五个 lab 后再读差异章节，
避免把本地实验成功误解成 Amazon S3 兼容性证据。

完整 M2 范围与最小 API 示例见
[中文 README](https://github.com/system-in-miniature/mini-s3/blob/main/README.zh-CN.md)。
[设计历史存档](../superpowers/README.md)反映建设期计划；正典文档与测试定义当前行为。
