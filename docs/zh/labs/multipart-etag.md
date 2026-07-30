# Lab：Multipart ETag 之谜

[English](../../labs/multipart-etag.md)

运行：

```bash
uv run python labs/lab_multipart_etag.py
```

lab 将 `same-bytes` 分别通过单 PUT 和两片 multipart 写入。两次 GET 的 body 相等，
ETag 却不同：

```text
same body: True
single PUT ETag: "e1d44c23b69953b35433ff067798318a"
multipart ETag: "05888a49b792dfb72298daafe3807667-2"
ETags differ: True
```

Multipart 公式不是 `md5(complete body)`，而是
`md5(part-1 MD5 二进制 digest || part-2 MD5 二进制 digest)-2`。若错误地哈希十六
进制 digest 文本，还会得到第三个值；这正是本实验要暴露的经典陷阱。

为了保持实验小巧，lab 把 MiniS3 可配置的最小 part 尺寸降为 3 字节。生产 S3 对
complete 清单中除最后一片外的常规下限为 5 MiB；MiniS3 的默认值也是 5 MiB。
