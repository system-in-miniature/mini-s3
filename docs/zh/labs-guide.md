# 第 4 章：动手实验

[English](../labs-guide.md)

先执行 `uv sync --dev`，再从仓库根目录运行命令。lab 使用临时目录与公开
`MiniS3` API，不会在仓库里留下对象数据。

## 版本控制与删除标记

源码：
[lab_versioning.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_versioning.py)

```bash
uv run python labs/lab_versioning.py
```

预期：两次 PUT 创建 `v00000001`、`v00000002`，DELETE 创建 `v00000003`。
删除标记成为最新条目，普通 GET 报告 `NoSuchKey`，按版本 GET 仍能读到
`draft one`。重点观察删除如何改变“最新”投影，而不销毁历史字节。

## 目录错觉

源码：
[lab_directory_illusion.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_directory_illusion.py)

```bash
uv run python labs/lab_directory_illusion.py
```

预期：系统只存储三个扁平键。不传 delimiter 时全部是 contents；根层使用
delimiter `/` 时只得到公共前缀 `photos/`；进入 `photos/` 后，
`photos/readme.txt` 是内容，年份路径是公共前缀。重点观察列表参数如何在没有
目录记录的情况下投影出层次。

## 崩溃原子性

源码：
[lab_crash_atomicity.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_crash_atomicity.py)

```bash
uv run python labs/lab_crash_atomicity.py
```

预期：manifest 发布前崩溃，重开看到完整的 `old`；发布后崩溃，重开看到完整的
`new`；不会看到部分对象体。重点观察 manifest rename 的可见性边界，并牢记
文档限定的 POSIX rename/fsync 假设。

## Multipart ETag 之谜

源码：
[lab_multipart_etag.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_multipart_etag.py)

```bash
uv run python labs/lab_multipart_etag.py
```

预期：两个对象的 body 完全相同。单 PUT 得到纯带引号 MD5；两片上传得到另一个以
`-2` 结尾的 ETag。重点观察 multipart ETag 的输入包含各 part 的二进制 digest 和
part 边界，而不只是 complete 后的字节。

## 条件 compare-and-swap

源码：
[lab_conditional_cas.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_conditional_cas.py)

```bash
uv run python labs/lab_conditional_cas.py
```

预期：两个并发写者复用同一个已观察 ETag。恰好一个成功存储替换值，另一个得到
`412 PreconditionFailed`；最终 body 是某个写者的完整值。重点观察 ETag 检查与变更
共用一个临界区，而不是退化成 check-then-write 竞态。

继续阅读 [Amazon S3 映射](mapping.md)和[已声明差异](DIFFERENCES.md)。
