> **Language**: [English](../mapping.md) | 简体中文

# MiniS3 ↔ Amazon S3 映射

以下标签用于区分忠实的教学机制、经过简化的表层，以及计划实现或明确排除的行为：

- **A — 对齐（aligned）：** 核心可观察机制与现代 S3 一致。
- **S — 简化（simplified）：** 教学机制已经具备，但缩减了生产环境的表层、规模或
  边界情况。
- **N — 未实现（not implemented）：** 刻意置于 M1 或本项目范围之外。

| MiniS3 concept | Real S3 concept | Level | Mapping |
|---|---|---:|---|
| Bucket | General purpose bucket | S | Named ownership boundary; no region, account, endpoint, or naming-rule model. |
| Flat string key | Object key | A | `/` is an ordinary character; neither system stores directories. |
| Whole-body PUT | PutObject | A | Replaces the complete current value rather than editing byte ranges in place. |
| Quoted content MD5 | Single-part ETag | S | Matches the familiar unencrypted single-part form only. |
| `null` version | Pre-versioning/suspended null version | A | One replaceable null slot coexists with named history after suspension. |
| Enabled version IDs | S3-generated version IDs | S | State transitions align; IDs are readable injected-counter values for determinism. |
| Delete marker | Delete marker | A | A marker becomes latest and hides older bytes without destroying them. |
| Version-addressed GET/DELETE | `versionId` query | A | Addresses one exact retained data version or marker. |
| `prefix` + `delimiter` | ListObjectsV2 grouping | A | `CommonPrefixes` is derived from key strings and request parameters. |
| Continuation token | ListObjectsV2 continuation token | S | Opaque and query-bound, but local and unsigned; no distributed snapshot lease. |
| Version listing | ListObjectVersions | S | Flattens all entries with `is_latest`; M1 omits markers/pagination fields from the wire API. |
| Manifest rename | Internal metadata commit | S | Teaches atomic visibility, not S3's distributed metadata architecture. |
| Startup recovery | Service recovery | S | Removes local tmp/orphan files; no replication or multi-node repair. |
| Multipart/conditions/lifecycle | Corresponding S3 APIs | N | M2 boundaries exist as docstrings, with no callable M1 behavior. |

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
