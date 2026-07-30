# MiniS3 教程

[English](../index.md)

MiniS3 是一个确定性的 Python 教学实现，覆盖 S3 风格对象存储的核心机制：
扁平键、带引号的 MD5 ETag、存储桶版本控制、删除标记、prefix/delimiter
列表查询，以及崩溃一致的本地发布。它提供直接 Python API，而不是兼容
HTTP/S3 的服务器。

## 安装

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/system-in-miniature/MiniS3.git
cd MiniS3
uv sync --dev
```

## 第一个实验

```bash
uv run python labs/lab_versioning.py
```

脚本写入两个版本、创建删除标记，展示普通 GET 此时得到 `NoSuchKey`，然后按
version ID 取回仍被保留的第一个版本。

## 阅读顺序

先通过仓库导览理解代码布局，再读概念映射。运行三个 lab 后再读差异章节，
避免把本地实验成功误解成 Amazon S3 兼容性证据。

完整 M1 范围与最小 API 示例见
[中文 README](https://github.com/system-in-miniature/MiniS3/blob/main/README.zh-CN.md)。
[设计历史存档](../superpowers/README.md)反映建设期计划；正典文档与测试定义当前行为。
