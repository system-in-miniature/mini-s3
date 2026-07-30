# 06 — 分片上传

## 学习目标

学完本章，你能够：

- 解释为什么分片在完成上传前对 GET 和 LIST 不可见；
- 说明何时才具备检查最小分片大小所需的信息；
- 从各分片的二进制 MD5 摘要推导 multipart ETag；
- 追踪暂存文件如何原子地发布成一个对象；
- 区分 MiniS3 忠实保留的状态机不变量与本地内存拼接这一简化。

## 机制讲解：私有分片，一次公开发布

大对象不适合在一次请求中上传。分片上传把过程拆成四种操作：初始化、上传编号分片、用有序清单完成，或中止。它不只是“切开字节串”，而是一套发布协议：分片是私有中间状态，只有成功完成才产生对象。

`src/minis3/multipart.py` 定义了这些状态。`MultipartUpload` 把 `upload_id` 绑定到桶和精确 key；`MultipartPart` 是返回给调用者的回执；`StagedPart` 是从私有存储恢复出的字节。它们有意与 `src/minis3/model.py::Version` 这一公开不可变对象值分开。

`src/minis3/store.py::MiniS3.create_multipart_upload` 在锁内确认桶存在，分配 `u00000001` 之类的确定性 ID，再调用 `src/minis3/storage/disk.py::DiskStorage.create_multipart_upload` 创建：

```text
buckets/<bucket>/uploads/<upload-id>/
  upload.json
  parts/
```

这里没有修改桶的 `ObjectRecord`。`MiniS3.list_objects` 读取桶记录而非 `uploads/`，所以未完成上传不会泄漏到 GET 或 LIST。这是语义边界，不是界面惯例。

`src/minis3/store.py::MiniS3.upload_part` 接受 1 到 10,000 的分片编号，创建 `StagedPart` 后交给 `DiskStorage.write_multipart_part`。后者先用 `DiskStorage.load_multipart_upload` 校验桶、key 与上传 ID 是否同 `upload.json` 一致，再通过 `src/minis3/storage/atomic.py::atomic_write` 发布分片。同一编号重新上传会原子替换暂存文件，不会新增公开版本。

为什么上传时允许小分片？因为此时服务不知道它最终是否是最后一片；成员和顺序由完成清单决定。因此 `src/minis3/multipart.py::validate_completion` 只检查 `selected[:-1]` 的 `minimum_part_size`。默认值 `MIN_PART_SIZE` 是 5 MiB，测试和实验可注入更小正数，避免为了讲规则分配大缓冲区。

完成操作不盲信客户端。`validate_completion` 会拒绝空清单、非严格递增的编号、缺失分片、过期或伪造的 ETag，以及过小的非末片。未被清单点名的暂存分片不会进入结果。因此完成清单是一份精确的提交声明。

multipart ETag 是经典陷阱。`validate_completion` 的核心是：

```python
digests = b"".join(
    md5(part.body, usedforsecurity=False).digest() for part in selected
)
composite = md5(digests, usedforsecurity=False).hexdigest()
```

外层哈希的输入是各分片 **二进制** 16 字节 MD5 摘要的拼接，不是可打印的十六进制字符串，也不是完整对象体。结果加引号并附 `-N`。因此最终字节相同，只要分片边界不同，ETag 就可能不同。

`src/minis3/store.py::MiniS3.complete_multipart_upload` 持有对象变更使用的同一把 `RLock`。它重载并校验分片，按序拼接 body，然后调用 `src/minis3/bucket.py::Bucket.put`，传入组合 ETag 和 `multipart_upload_id`。候选桶由 `src/minis3/storage/disk.py::DiskStorage.persist_bucket` 持久化：先写不可变对象工件，最后原子替换 `manifest.json`。manifest 发布是可见性点，之后才删除暂存区。

这个顺序也处理崩溃窗口：若对象 manifest 已落盘而暂存尚未清理，重启时 `DiskStorage._recover_uploads` 会从已发布版本的 `multipart_upload_id` 识别并删除残留；若崩溃发生在 manifest 发布前，旧对象状态仍是权威，持久的未完成上传还可继续。

`MiniS3.abort_multipart_upload` 调用 `DiskStorage.remove_multipart_upload`：先把暂存目录改名为墓碑，fsync 上传目录，再删除墓碑并再次 fsync。它不会影响已经可见的对象。

### 沿故障路径阅读

校验发生在创建候选 `Bucket` 之前，所以 `InvalidPartOrder`、`InvalidPart` 或 `EntityTooSmall` 都不会改变公开对象或私有暂存。调用者可以补传替换分片，或用同一 upload ID 重新提交正确清单，无需回滚半完成事务。

校验通过后，完成操作进入普通持久化路径。若 manifest 改名前失败，恢复仍信任旧 manifest，新对象工件会作为孤儿清理，暂存仍可恢复；若已经跨过改名点，即使客户端没收到返回，对象也已经提交，重启会清掉暂存。这是典型的“响应丢失但服务器状态明确”的提交边界。

版本化并没有另一套 multipart 状态机。完成操作复用 `Bucket.put`：未版本化或暂停状态按普通规则替换 `null` 槽，启用状态创建新命名版本并保留历史。`Version` 仅额外记录组合 ETag 和用于恢复清理的上传 ID。新的写入路径不应偷偷发明不同的版本语义。

分片回执描述该编号当前暂存字节。重传 1 号分片会改变回执；携带旧回执的完成清单会失败，而不是静默选中新字节。因此回执能发现上传与完成之间的意外替换，但它不是认证凭据或全局对象 ID。

## 对照真实 Amazon S3

MiniS3 保留了可辨认的状态机不变量：创建得到 upload ID；编号范围 1–10,000；同号覆盖；完成提交有序编号与 ETag；除末片外通常至少 5 MiB；中止丢弃未完成状态；本章所建模的 multipart ETag 公式也与常见 MD5 形式一致。

边界同样重要。真实 S3 支持超大对象、并行网络传输、列出上传/分片、UploadPartCopy、其他校验和、权限、计费、遗留上传生命周期清理、受加密影响的 ETag 以及分布式持久性。MiniS3 不具备这些能力；它在内存中拼接全部分片并发布到单个 POSIX 文件系统。

准确分类见 [mapping 的 multipart 条目](../mapping.md)。[DIFFERENCES 的 Multipart 与 ETag 条目](../DIFFERENCES.md) 明确否认“所有生产 ETag 都是 MD5 内容哈希”以及“本地 fsync 等于 S3 持久性”。

## 动手实验

```bash
uv run python labs/lab_multipart_etag.py
```

本仓实测输出：

```text
same body: True
single PUT ETag: "e1d44c23b69953b35433ff067798318a"
multipart ETag: "05888a49b792dfb72298daafe3807667-2"
ETags differ: True
```

body 相等，说明 ETag 差异不可能只由最终字节决定。第一个来自 `src/minis3/model.py::content_etag`，第二个来自 `validate_completion`，其中 `b"same-"` 与 `b"bytes"` 各自贡献二进制摘要。实验把最小分片设为 3，不会改变默认值。

还可运行：

```bash
uv run pytest -q tests/test_multipart.py
```

它覆盖完成前不可见、有序原子发布、同号替换、全部清单错误、重启保留、中止、身份校验和编号边界。

## 练习

1. **理解题。** 为什么在 `upload_part` 中检查最小大小会拒绝合法上传？

??? note "参考答案"
    “最后一片”由之后的完成清单定义，小分片可能合法地成为末片。上传时上下文不足；`validate_completion` 检查选中分片中除末片外的部分才正确。

2. **理解题。** `md5(part1.etag.encode() + part2.etag.encode())` 有哪两个错误？

??? note "参考答案"
    输入应是原始 16 字节摘要，不是带引号的十六进制文本；组合结果还需加引号和 `-2`。实现对每个 body 调 `.digest()`，仅外层调用 `.hexdigest()`。

3. **动手题。** 不改 `src/`，把实验复制到 `/tmp`，将 `same-bytes` 切成 `b"s"`、`b"ame-"`、`b"bytes"`，把最小分片设为 1，并先预测后运行。

    验收：输出 `same body: True`、multipart 后缀 `-3`、`ETags differ: True`。

??? note "参考答案"
    改为三次编号 1、2、3 的上传，并按递增顺序传入三个回执。边界改变会改变精确十六进制值，但完成 body 仍是 `same-bytes`。

4. **动手题。** 编写 `/tmp/multipart-order.py`，上传 1、2 两片后以 `[part2, part1]` 完成。

    验收：运行时捕获并打印 `InvalidPartOrder`，随后 GET 仍抛 `NoSuchKey`。

??? note "参考答案"
    使用 `TemporaryDirectory`，显式捕获 `InvalidPartOrder` 和 `NoSuchKey`。失败发生在 `Bucket.put` 和 manifest 发布前，因此没有公开对象。

## 小结

分片上传是一套小型事务协议：持久的私有分片只有在有序清单通过校验并跨过桶 manifest 发布点后，才成为一个公开不可变值。由此可以统一解释末片大小例外、同号替换、恢复和组合 ETag。下一章会把 ETag 用于另一件事：以条件请求保护读写。
