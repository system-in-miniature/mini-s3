# 07 — 条件请求

## 学习目标

学完本章，你能够：

- 求值 MiniS3 简化的 `If-Match` 与 `If-None-Match`；
- 区分 304 形态的缓存结果与 412 形态的前置条件失败；
- 解释为何条件变更必须在同一把锁内比较并发布；
- 把 ETag 用作乐观并发令牌；
- 识别 direct API 有意省略的协议和 ETag 情形。

## 机制讲解：把观察变成前置条件

普通 GET 问“对象现在是什么”；条件请求带上先前观察：“仅在它变化后返回”，或“仅在它仍是我见过的版本时执行”。ETag 由被动元数据变成了控制输入。

纯匹配规则位于 `src/minis3/conditional.py`。`etag_matches` 按逗号拆分、去除空白并精确比较字符串。候选中有 `*` 时，只要当前对象存在就匹配；否则至少一个候选必须等于当前带引号 ETag。当前对象不存在时永不匹配。

它有意不处理弱验证器、不删除引号，也不解析完整 HTTP 语法。调用者传入包含引号的精确值。这足以揭示机制，却不冒充 HTTP 实现。

两个包装函数命名了不同结果。`require_if_match` 在条件不匹配时抛 `src/minis3/errors.py::PreconditionFailed`，代表 HTTP 412：操作前提为假。`require_if_none_match` 在条件匹配时抛 `NotModified`；对 GET 而言代表 HTTP 304：缓存表示仍有效，无需传输 body。

`src/minis3/store.py::MiniS3.get_object` 先经 `Bucket.get` 找到当前或指定版本，再依次检查 `If-Match`、`If-None-Match`。只有两者都允许才返回不可变 `Version`。因为这是 direct Python API，异常代替 HTTP 状态行，也没有真正的无 body 网络响应。

条件写展示了更深的并发问题。`MiniS3.put_object` 获取进程内 `RLock`，深拷贝桶，通过 `MiniS3._current_etag` 读取当前可见 ETag，调用 `require_if_match`，用 `Bucket.put` 修改候选，持久化后替换内存桶。比较和发布处于同一串行临界区。

下面的写法是错误的：

```python
current = store.get_object("b", "k")
if current.etag == expected:
    store.put_object("b", "k", replacement)
```

两个调用各自线程安全，但另一写者可在 GET 释放锁与 PUT 获取锁之间发布。两个客户端可能看到相同旧值并都覆盖它。正确方式是 `put_object(..., if_match=expected)`，由存储层拥有原子 CAS 边界。

这就是乐观并发控制：读者不持有长租约，而是读取令牌、独立计算、提交时呈交令牌。令牌过期就失败，避免静默抹掉胜者更新。调用者可按业务策略重读、合并、重试或报告冲突。

`MiniS3.delete_object` 使用同一模式，但调用 `MiniS3._addressed_etag`。没有 version ID 时比较当前可见对象；有 ID 时比较该精确数据版本。缺 key、缺版本或当前是删除标记都没有 ETag，因此连 `If-Match: *` 也失败。星号意为“存在当前表示”，不是“无条件执行”。

在启用版本化的桶里，成功的条件 PUT 产生新版本；旧 ETag 仍属于历史版本，但不再是当前令牌。无 version ID 的条件 DELETE 先检查当前数据 ETag，再创建删除标记。旧版本仍能按 ID 获取，却不会让过期的当前条件成功。

锁只给出单进程线性化顺序。`DiskStorage.persist_bucket` 仍通过原子 manifest 改名发布胜者；失败的前置条件在写任何工件前结束，成功调用则在本地发布完成后返回。

### 读条件、写条件与重试策略

同一谓词服务于不同目标。GET + `If-None-Match` 是缓存再验证，匹配意味着可复用缓存；GET + `If-Match` 是受保护读取，不匹配表示假设已过时；PUT/DELETE + `If-Match` 是受保护变更，不匹配可防丢失更新。语法相同，成功与失败的含义不同。

412 不是“盲目循环”的指令。若两个工作者各改 JSON 的不同字段，失败者拿新 ETag 重放旧完整 body，仍会抹掉胜者。正确应用应重读并重算或合并。MiniS3 只报告冲突，把领域策略留给调用者。

真实网络还存在“不确定提交”：请求发送后连接丢失，客户端不知道服务是否提交。MiniS3 无网络，本地方法会返回或抛错；但服务器侧仍以恢复后的 manifest 为权威。生产适配器可能需要请求 ID 或应用层幂等。ETag CAS 防止过期替换，却不识别重复请求。

逗号分隔候选允许缓存或迁移客户端接受多个已知表示。`etag_matches` 去空白后，任一精确候选匹配即可。但弱标签 `W/"..."`、特殊 HTTP 文法以及日期条件优先级属于未来协议层，不能从这个 helper 推断。

## 对照真实 Amazon S3

真实 S3 通过 HTTP 条件头暴露这些能力。HTTP 还规定方法、日期、实体标签列表、弱验证器、状态码和响应头的交互；S3 对并发条件操作及部分 API 还有服务特有规则。

MiniS3 只保留窄范围核心不变量：精确带引号 ETag、`*`、逗号候选；GET 匹配 `If-None-Match` 得到 304 形态 `NotModified`；不满足 `If-Match` 得到 412 形态 `PreconditionFailed`；单进程内条件 PUT/DELETE 原子化。它没有 HTTP 适配器、完整头优先级、请求 ID、认证、分布式冲突协议或多进程锁。

真实 S3 客户端应把 ETag 当不透明验证器。加密、multipart 布局等意味着它不总是完整 body 的 MD5。应比较服务返回值，而非自行重算假想值。参见 [mapping 的条件请求与 CAS](../mapping.md) 以及 [DIFFERENCES 的 Conditions 与 Concurrency](../DIFFERENCES.md)。

## 动手实验

```bash
uv run python labs/lab_conditional_cas.py
```

本仓实测输出：

```text
outcomes: ['stored', '412 PreconditionFailed']
one winner: True
one 412: True
final body is complete: True
```

谁赢受调度影响，所以实验只打印稳定不变量：一个成功、一个 412。`Barrier(2)` 让两者共享观察到的 ETag；`MiniS3.put_object` 串行比较，第一个改变当前 ETag，第二个就面对过期状态。

聚焦测试：

```bash
uv run pytest -q tests/test_conditional.py
```

它覆盖 GET 匹配/不匹配、通配存在性、条件 PUT/DELETE 和双写竞争。

## 练习

1. **理解题。** 为什么“线程安全 GET 后接线程安全 PUT”不是 CAS？

??? note "参考答案"
    单次调用安全不等于二者不可分割。另一写者可在两次加锁之间发布。`put_object(if_match=...)` 在一把锁内求值并修改，不允许变更插入。

2. **理解题。** MiniS3 中 `If-Match: *` 与 `If-None-Match: *` 是什么含义？

??? note "参考答案"
    仅当存在当前数据 ETag 时 `etag_matches("*", current)` 为真。因此前者要求存在；后者在对象存在时产生 `NotModified`。缺失 key 或当前删除标记都不匹配。

3. **动手题。** 写 `/tmp/cache-check.py`：PUT `b"value"`，用其 ETag 做 `if_none_match` GET，并打印捕获的异常名。

    验收：输出 `NotModified`；普通 GET 仍返回 `b'value'`。

??? note "参考答案"
    使用 `TemporaryDirectory`，仅捕获 `NotModified`，之后无条件 GET。该异常是控制结果，不是删除或损坏；不要修改 `src/`。

4. **动手题。** 在 `/tmp` 的 CAS 实验副本中，让失败者重读新 ETag 后再重试一次。

    验收：第一轮仍是一成功一 412；显式重试成功，最终 body 等于重试值。

??? note "参考答案"
    保留原竞争。线程池关闭后读取 `latest`，再以 `latest.etag` 和独特 body 调用 `put_object`。这展示应用拥有冲突策略，而存储 CAS 边界不被削弱。

## 小结

条件请求让先前观察可以约束当前操作。纯匹配规则给出 304/412 形态结果，存储锁则把 `If-Match` 与变更组合成真正的单进程 CAS。正确客户端把 ETag 当不透明令牌，并明确选择重试或冲突策略。下一章将引入另一类策略边界：先纯粹、确定性地选择时间动作，再原子应用。
