# 09 — 方法论与边界

## 学习目标

学完本章，你能够：

- 把 MiniS3 读成一组明确的语义与持久性边界；
- 将论断分类为等价、有意简化或未实现；
- 把测试、实验、mapping 与 DIFFERENCES 当作互补证据；
- 说明纠删码、存储类别和复制需要改变哪些机制；
- 在不暗示 S3 兼容的前提下设计有源码依据的扩展。

## 机制讲解：系统缩影，而非 mock

MiniS3 小，是因为它选择了机制，而不是因为正确性可选。简单 mock 可能只做 `dict[(bucket, key)] = bytes`；MiniS3 保留了值得研究的边界：平面 key、不可变版本、桶状态转换、投影式 listing、私有 multipart 暂存、条件 CAS、显式生命周期决策和崩溃一致发布。

公共边界是 `src/minis3/store.py::MiniS3`。其方法像本地 SDK，负责调用级同步并协调领域状态与存储；它有意不是 HTTP 服务。未来适配器可把请求翻译为这些方法，但协议解析不应接管版本、ETag 或持久语义。

领域边界被拆为专注模块。`src/minis3/model.py::Version`、`DeleteMarker`、`ObjectRecord` 定义不可变历史；`src/minis3/bucket.py::Bucket.put/delete` 拥有版本状态机；`src/minis3/listing.py::list_objects` 从平面 key 派生 prefix/delimiter 视图；`src/minis3/multipart.py::validate_completion`、`conditional.py::etag_matches`、`lifecycle.py::evaluate_expiration` 把纯决策与 I/O 隔离。

持久边界在 `src/minis3/storage/atomic.py::atomic_write` 与 `src/minis3/storage/disk.py::DiskStorage.persist_bucket`。字节和不可变元数据先 fsync，最后原子替换 `manifest.json`；改名是本地可见性点。`DiskStorage.load_buckets` 信任已发布 manifest，并清理临时或孤儿工件。这给出有意义的 POSIX 崩溃模型，却不声称磁盘冗余或分布式元数据。

阅读任一操作时可问四个问题：

1. 哪个公共方法拥有事务？
2. 哪个纯函数/领域函数决定状态转换？
3. 哪个持久工件表示结果？
4. 哪个事件让结果可见？

multipart 完成的答案是 `MiniS3.complete_multipart_upload`、`validate_completion` + `Bucket.put`、被桶 manifest 引用的不可变版本文件、manifest 改名。条件 PUT 的答案是 `MiniS3.put_object`、`require_if_match` + `Bucket.put`、相同版本工件、相同改名点。相同答案说明架构复用，而非重复实现特性。

### 三种不同证据

源码解释实现，却不能单独证明观察合同。`tests/` 是可执行规格：版本测试钉住不可逆启用、null 版本和删除标记；listing 测试钉住目录幻觉与分页；storage 测试在发布点周围注入崩溃；M2 测试覆盖 multipart、条件和生命周期。全绿只说明当前环境内这些本地合同通过，不认证范围外行为。

`labs/` 是叙事实验，只打印少量可解释事实：保留版本、分组 prefix、崩溃旧或新结果、multipart ETag 差异、CAS 唯一胜者。它们适合建立心智模型，测试则适合守护更多边界。

[mapping](../mapping.md) 与 [DIFFERENCES](../DIFFERENCES.md) 约束解释。“Equivalent”指命名不变量在边界内一致，不代表可替换 S3；“Intentional simplification”指概念存在但协议、规模、编排或边角被缩小；“Not implemented”表示没有可调用行为。DIFFERENCES 汇总表格可能掩盖的跨领域缺口。

这样既避免过度声称“ETag 一样所以兼容 S3”，也避免把本地 Python 贬成毫无真实价值。准确表述应同时说出不变量和边界，例如：“MiniS3 实现常见的二进制分片摘要 ETag 与本地原子发布，但不实现 S3 分布式服务、线协议或普遍 ETag 语义。”

### 如何继续越过当前边界

纠删码不是“把文件切成 multipart”。multipart 是上传协议，结果仍是一个逻辑对象；纠删码是物理布局：编码数据/校验分片，跨故障域放置，校验、重建与修复。合理扩展应保留 `Version` 作为逻辑值，泛化 `DiskStorage` 工件，并增加 shard manifest、放置策略、quorum/持久规则、故障注入和重建测试；发布仍必须一次性暴露完整逻辑版本。

存储类别也不只是字符串字段。近生产模型需要类别对应的放置/持久策略、安全复制或重编码转换、归档恢复状态，以及在声称时实现费用与最短保存期。生命周期目前只返回过期动作；可新增转换动作，但验收必须覆盖搬迁崩溃，确保 manifest 永不指向不完整数据。

复制不是 PUT 后复制根目录。分布式系统必须定义操作日志或状态传输、顺序、确认、重试幂等、延迟、旧 leader fencing、冲突和读一致性。当前 CAS 依赖一把 `RLock`；跨进程/地域需要元数据共识/串行机制，或明确较弱冲突模型。本地 fsync 不能建立复制持久性。

HTTP/S3 适配器也是独立层：路由、XML、状态码/头优先级、流式 body，以及声称兼容时的认证签名和真实服务差分测试。它应翻译 `NoSuchKey`、`NotModified`、`PreconditionFailed`，不应重写桶状态机。在该层存在前，socket 或真实 S3 客户端实验均标为 **需运行时验证**，不能声称支持。

安全和运维还包括 IAM/桶策略、加密与轮换、配额、审计、指标、后台 scrub/repair、容量、升级和多租户隔离。每项都需要所有权边界和故障合同，仅在 README 中写名字不算实现。

## 对照真实 Amazon S3

Amazon S3 是托管、多租户、区域化服务，具有分布式元数据与存储、复制修复、授权、加密、校验和、多存储类别、自动生命周期、事件、计费、可观测性以及签名 HTTP API。其内部实现不是这里的本地 manifest 架构。

MiniS3 只在明确映射的可观察切片上对齐：平面 key、整对象替换、删除标记、prefix/delimiter 分组、所建模的 multipart ETag、对象级条件语义。确定性 ID、单进程锁、数值时钟、本地 manifest、简化 token、手动生命周期和直接异常都是教学选择。

使用任何等价论断前先查 [完整行为映射](../mapping.md)，再查 [明确非目标与语义差异](../DIFFERENCES.md)。它们是产品合同，不是事后道歉。

## 动手实验

```bash
uv run pytest -q
```

本仓实测输出：

```text
.................................................                        [100%]
49 passed in 3.72s
```

这证明当前环境中 49 个仓库测试通过，覆盖 direct Python 行为和测试触及的本地 POSIX 崩溃模型；它不验证 HTTP、真实 S3、多进程/多机、纠删码、复制、IAM、加密或存储类别。

再列出机制所有者：

```bash
rg -n '^    def (put_object|complete_multipart_upload|lifecycle_tick)|^def (list_objects|validate_completion|etag_matches|evaluate_expiration|atomic_write)' src/minis3
```

逐个命中应用上述四问。行号会演进，相对路径与函数名才是稳定教程锚点。

## 练习

1. **理解题。** 为什么 mapping 中 “Equivalent” 不等于“可直接替换”？

??? note "参考答案"
    分类仅针对边界内一个命名不变量；可替换还需线协议、认证、完整错误/头、规模并发语义和其余 API。可用性与语义级别是分开记录的。

2. **理解题。** 纠删码应归 multipart、桶状态机还是存储边界所有？为什么？

??? note "参考答案"
    存储拥有 shard 编码、放置、重建和修复，因为这些改变一个逻辑不可变版本的物理表示。multipart 仍是上传协议，桶仍拥有逻辑历史，服务协调发布。

3. **动手题。** 创建 `/tmp/minis3-evidence.md`，为 multipart ETag、条件 CAS、HTTP 兼容、复制各写一行，列出源码锚点、可执行证据、语义等级和可用性。

    验收：前两行引用函数和测试/实验；HTTP 与复制标未实现且不伪造成功实验；每行链接 mapping 或 DIFFERENCES。

??? note "参考答案"
    multipart 可引 `multipart.py::validate_completion` 与 `tests/test_multipart.py`；CAS 引 `store.py::MiniS3.put_object` 与 `tests/test_conditional.py`。HTTP/复制没有可调用实现，应记录非目标。

4. **动手题。** 不改 `src/`，为未来存储类别转换草拟五项测试验收。

    验收：覆盖可见语义、发布前崩溃、发布后崩溃、重启恢复/清理、转换期间或之后读取，并命名所有者和可见性点。

??? note "参考答案"
    让 `MiniS3` 协调、新增存储转换与生命周期动作，保留 manifest 改名为可见性点。证明只见旧或新类别、对象不缺失/撕裂、恢复确定、孤儿清理、读取字节相同；未实现时不声称费用语义。

## 小结

MiniS3 最持久的课程是一套方法：保留真实语义边界，隔离决策与副作用，定义可见性点，在其周围测试故障，并只按证据粒度声称等价。本仓在分布式 S3 架构开始前结束，却给出了继续前进的精确地图；新特性应扩展这些所有权与发布合同，而不是仅使用生产系统相似的名字。
