> **语言**: [English](../mapping.md) | 简体中文

# MiniS3 ↔ Amazon S3 映射

**语义档位（Semantic tier）**使用系列统一的三个值：

- **等价（Equivalent）：** 在本项目声明的边界内，具名的可观察不变量与现代 S3
  一致。
- **有意简化（Intentional simplification）：** 保留相同理念，但缩减了生产协议、
  规模、编排或边界情况。
- **语义相反（Semantically opposite）：** 实现采用了 S3 有意不采用的路径；当前
  M2 没有任何一行属于此分类。

**可用性（Availability）**单独标记为**可用（Available）**或
**未实现（Not implemented）**：前者表示可调用的 M2 行为，后者表示只有计划边界或
明确非目标。

| MiniS3 概念 | 真实 S3 概念 | 语义档位 | 可用性 | 映射 |
|---|---|---|---|---|
| 存储桶（Bucket） | 通用存储桶（General purpose bucket） | 有意简化 | 可用 | 具名所有权边界；没有区域、账户、端点或命名规则模型。 |
| 扁平字符串键 | 对象键（Object key） | 等价 | 可用 | `/` 是普通字符；两个系统都不存储目录。 |
| 完整对象体 PUT | PutObject | 等价 | 可用 | 替换完整的当前值，而不是原地编辑字节范围。 |
| 带引号的内容 MD5 | 单段 ETag（Single-part ETag） | 有意简化 | 可用 | 只匹配常见的未加密单段形式。 |
| `null` 版本 | 启用版本控制前/暂停后的空版本 | 等价 | 可用 | 暂停后，一个可替换的空槽位与具名历史版本并存。 |
| 已启用的版本 ID | S3 生成的版本 ID | 有意简化 | 可用 | 状态转换一致，包括启用后不可逆；为了确定性，ID 使用可读的注入计数器值。 |
| 删除标记（Delete marker） | 删除标记 | 等价 | 可用 | 标记成为最新版本并隐藏较旧字节，但不会销毁它们。 |
| 按版本寻址的 GET/DELETE | `versionId` 查询 | 等价 | 可用 | 精确寻址一个保留的数据版本或标记。 |
| `prefix` + `delimiter` | ListObjectsV2 分组 | 等价 | 可用 | `CommonPrefixes` 由键字符串和请求参数派生。 |
| 延续令牌（Continuation token） | ListObjectsV2 延续令牌 | 有意简化 | 可用 | 不透明且与查询绑定，但仅限本地且无签名；没有分布式快照租约。 |
| 版本列表 | ListObjectVersions | 有意简化 | 可用 | 将所有条目展平并附带 `is_latest`；MiniS3 的线协议 API 省略标记/分页字段。 |
| 清单重命名（Manifest rename） | 内部元数据提交 | 有意简化 | 可用 | 用于讲解原子可见性和完整的本地目录 fsync 链，而非 S3 的分布式元数据架构。 |
| 启动恢复 | 服务恢复 | 有意简化 | 可用 | 移除本地临时文件/孤儿文件；没有复制或多节点修复。 |
| Multipart 状态机 | CreateMultipartUpload / UploadPart / CompleteMultipartUpload / AbortMultipartUpload | 有意简化 | 可用 | 具备持久私有暂存、有序回执校验、最后一片尺寸例外、abort 与原子发布；本地在内存组装，并省略 upload listing、MD5 之外的校验和及分布式编排。 |
| Multipart ETag | Multipart 对象 ETag | 等价 | 可用 | 精确实现带引号的 `md5(各 completed part 的 MD5 二进制拼接)-N`，刻意区别于完整 body MD5。 |
| GET ETag 条件 | `If-Match` / `If-None-Match` | 等价 | 可用 | 精确/current 通配匹配产生 412/304 形态结果；直接 API 以具名异常代替 HTTP 响应。 |
| 条件 PUT/DELETE | S3 conditional writes | 等价 | 可用 | ETag 比较和变更共用一个串行临界区，陈旧写者得到 `PreconditionFailed`。 |
| Expiration tick | Lifecycle current/noncurrent expiration | 有意简化 | 可用 | 纯 prefix/age 规则在注入时间手动求值；版本化桶的当前数据产生 marker，noncurrent 数据被物理删除。没有后台调度或 storage-class 迁移。 |

## 为什么 multipart ETag 不是内容哈希

单 PUT `same-bytes` 得到完整字节的带引号 MD5。把相同字节分成两片上传，则会对两份
**二进制** part digest 再做 MD5，并追加 `-2`。因此 part 边界也是 ETag 输入：最终
body 相同，ETag 仍完全可能不同。

MiniS3 忠实保留这个常被忽略的 S3 行为，但不声称所有真实 S3 ETag 都源自 MD5；
加密和其他服务实现选择不在等价边界内。

## 条件写为何构成 CAS

只有当“比较当前 ETag”和“发布替换值”不会被另一个写者插入时，`If-Match` 才能作为
CAS。MiniS3 在 store 写锁内完成二者。两个写者使用同一份观察到的 ETag 时只能有
一个胜者；其发布改变 ETag 后，另一方得到 S3 形态的 `PreconditionFailed`。

## 为什么列表查询会产生目录错觉（directory illusion）

假设仅存储了 `photos/2025/a.jpg` 和 `photos/2026/b.jpg` 这两个键。不指定分隔符的
列表查询会返回两个键。改用 `prefix="photos/"` 和 `delimiter="/"` 进行列表查询，
则会返回 `photos/2025/` 和 `photos/2026/` 这两个字符串作为公共前缀
（common prefixes）。没有任何内容被创建、移动或遍历：服务器只是以该前缀之后的
第一个分隔符为界，对匹配的扁平字符串进行了分组。

## 列表一致性于 2020 年 12 月发生变化

在 **2020-12-01** 之前，Amazon S3 文档将部分覆盖写入和列表查询观察描述为最终
一致性（eventual consistency）：一次成功的写入可能短暂地未出现在后续列表中，
或者列表可能呈现较旧的视图。这段历史解释了为什么较早的 S3 设计经常添加一致性
索引。

在 **2020-12-01**，AWS 宣布所有区域中的 S3 GET、PUT 和 LIST 操作（以及相关的
元数据更改操作）均提供强读后写一致性（strong read-after-write consistency）。
现代调用方可以预期，成功写入会立即反映在后续列表查询中。

MiniS3 与 2020 年后的模型对齐。每次调用都会持有存储锁（store lock），并根据当前
已发布的清单状态（manifest state）构建结果。变更在清单重命名时变得可见，因此列表
查询看到的要么是完整的旧状态，要么是完整的新状态。分页令牌（pagination tokens）
表示位置，而不是冻结的多次调用快照；因此，分页之间的并发更改可能改变后续页面的
成员构成，如 `DIFFERENCES.md` 中所述。
