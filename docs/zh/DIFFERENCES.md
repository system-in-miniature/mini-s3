> **Language**: [English](../DIFFERENCES.md) | 简体中文

# 与 Amazon S3 的差异

本文档是如实说明边界：MiniS3 用于讲授选定的机制，并非一个与 S3 线协议兼容、
安全或分布式的 S3 替代品。

## 明确的非目标

- IAM、存储桶策略、ACL、账户、租户和授权
- 服务端或客户端加密（encryption）以及密钥管理
- 存储类（storage classes）、归档恢复和存储类迁移
- 跨存储桶、区域或机器的复制（replication）
- 纠删码（erasure coding，一种可能的 M3 教学扩展）
- 预签名 URL（presigned URLs）
- S3 XML/HTTP 线协议、DNS 端点和请求签名
- 事件通知（event notifications）
- 配额（quotas）、计费、区域放置和生产环境存储桶名称验证

## M2 的简化和语义差异

- **ETag：** 单 PUT 使用带引号的完整 body MD5；multipart complete 忠实使用
  `md5(concatenated binary part MD5 digests)-N`。真实 S3 的 ETag 仍不一定源自
  MD5，因为加密和其他服务实现选择可能改变其含义。
- **版本 ID（Version IDs）：** 真实 S3 的 ID 是由服务生成的不透明字符串。
  MiniS3 刻意使用注入的单调递增值（`v00000001`、……），以便测试、恢复和实验可复现。
- **时间（Time）：** 版本保存数值创建时间。测试与 lifecycle lab 注入时钟；
  普通 store 默认使用进程挂钟。MiniS3 不建模完整 S3 Last-Modified 响应格式。
- **HEAD：** `head_object` 返回与 GET 相同的不可变 `Version` 值，包括本地可用的
  字节内容。由于没有传输层，MiniS3 不对无响应体的 HTTP HEAD 响应进行建模。
- **错误（Errors）：** Python 异常类表示 S3 形态的结果。不存在 HTTP 状态行、
  XML 错误文档、请求 ID 或删除标记响应头。
- **列表查询（Listing）：** 键和公共前缀按字典序排列，并共同计入 `max_keys`。
  令牌是不透明的，并与前缀和分隔符绑定，但它没有签名，也不会固定一个分布式快照。
  页面请求之间的变更可能移动分页边界。
- **版本列表（Version listing）：** MiniS3 在一个简化的结果中返回所有匹配的版本和
  删除标记。它省略了 S3 的键/版本标记、分页、所有权、时间戳和编码选项。
- **并发（Concurrency）：** 单个进程使用锁对调用进行串行化。不存在多进程锁、
  分布式事务、仲裁或冲突协议。
- **持久性（Durability）：** fsync + 原子重命名提供本地文件系统的崩溃边界。
  它不承诺复制持久性、磁盘容错、位腐烂修复（bit-rot repair），也不承诺在违反
  POSIX rename/fsync 预期的文件系统上的行为。
- **恢复（Recovery）：** 已发布的清单具有权威性。启动时会删除临时目录/文件，
  以及未被该清单引用的产物；不存在在线清理器或受损清单修复。
- **存储桶表层（Bucket surface）：** 存储桶不具备区域、所有权控制、对象锁、
  标签、网站配置、CORS、日志或生产环境命名规则。
- **Multipart：** upload 暂存持久且私有，但没有 list uploads/parts API、upload
  自动过期、并行流式组装器、其他 checksum family、copy-part 或 5 TiB 规模模型。
  Complete 先在内存拼接 part，再进入普通本地 atomic-write/manifest 发布路径。
- **条件请求（Conditions）：** 直接 API 接受精确带引号 ETag、逗号分隔候选与
  `*`；不解析 weak validator，也不复刻完整 HTTP header 优先级矩阵。
  `NotModified` 与 `PreconditionFailed` 分别代替 304 和 412 响应。
- **生命周期（Lifecycle）：** 规则随每次显式 tick 传入，而非保存为 bucket 配置。
  noncurrent 版本也从创建时刻计算 age；真实 S3 的 noncurrent-day 语义从版本变为
  noncurrent 时开始。未版本化 current expiration 物理删除 null 对象；版本化
  current expiration 产生 marker。
