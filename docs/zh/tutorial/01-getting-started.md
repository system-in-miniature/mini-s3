# 第 1 章：认识 MiniS3

MiniS3 不是把 Amazon S3 的每项功能都缩小后做成的克隆。它是一个小型、确定性的
对象存储，让一组经过取舍的机制保持可读：扁平 key、不可变对象值、版本历史、列表
投影、崩溃原子发布、分片完成、条件写，以及生命周期过期。本章先运行项目，再用一个
桶和一个对象确立边界；后续章节将在此基础上逐层深入。

## 学习目标

完成本章后，你将能够：

- 通过直接 Python API 创建临时 MiniS3 存储、桶和对象；
- 沿 `MiniS3.put_object` 跟踪第一次写入，并解释返回的 `Version`；
- 区分桶、对象 key、对象值、版本 ID 和 ETag；
- 找到持久化根目录，并解释一次性实验为什么使用临时目录；
- 明确 MiniS3 没有证明 Amazon S3 服务的哪些性质。

## 1. 为什么阅读一个微型系统？

生产对象存储同时包含公开协议、认证、多租户控制面、分布式元数据、复制、放置、
修复、计费和巨大的运维规模。这些问题很重要，但会遮住初学者最先需要回答的小问题：
key 中的斜杠是不是目录分隔符？成功 PUT 后究竟什么变得可见？开启版本控制后，
DELETE 是什么意思？原子提交点在哪里？

MiniS3 保留这些问题，去掉无关规模。仓库的公开边界是
`src/minis3/store.py` 中的 `MiniS3` 类。模块文档明确说明：这是形似 SDK 的服务
门面，不是 HTTP 服务器。`MiniS3.__init__` 接受文件系统根目录，构造
`DiskStorage`，通过 `DiskStorage.load_buckets` 重新载入已发布的桶，再创建一个
`threading.RLock`，把进程内调用串行化。这已经给出一条重要系统课：API 很窄不等于
“只存在内存里”。门面协调内存视图和持久表示。

构造函数还暴露三个教学接缝：

```python
def __init__(
    self,
    root,
    *,
    counter=None,
    crash_injector=None,
    clock=None,
    minimum_part_size=MIN_PART_SIZE,
):
```

`counter` 让 ID 确定，`crash_injector` 把文件系统边界变成可复现实验，`clock`
让时间规则可测试。真实服务不能暂停时间，也不能要求进程在某一具名代码行崩溃；
教学内核可以。正是这种可控性让机制更容易观察。

## 2. 环境与仓库地图

MiniS3 需要 Python 3.12 或更高版本，并使用
[uv](https://docs.astral.sh/uv/) 管理项目环境。在仓库根目录运行：

```bash
uv sync --dev
uv run pytest -q
```

运行时没有第三方依赖；pytest 是开发依赖。`uv run` 很重要，因为它选择锁定的项目
环境，并正确安装 `src/minis3` 包。直接调用系统 Python 可能找不到该包。

主要阅读路径如下：

| 路径 | 职责 |
|---|---|
| `src/minis3/store.py` | 公开多桶 API 与变更锁 |
| `src/minis3/model.py` | 不可变数据版本、删除标记和 ETag |
| `src/minis3/bucket.py` | 单桶记录与版本控制状态机 |
| `src/minis3/listing.py` | 当前和历史列表投影 |
| `src/minis3/storage/` | 文件系统布局、发布与恢复 |
| `labs/` | 确定性机制演示 |
| `tests/` | 可执行的语义与崩溃边界契约 |

不要从头到尾先读完每个文件。应从一个公开调用出发，跟随它拥有的状态，直到抵达
持久化边界。下一节将对 PUT 这样做。

这种沿调用阅读的纪律还能区分接口证据与实现证据。在 `__init__.py` 看到
`put_object`，只能证明方法可公开到达，尚不能证明持久化、替换或恢复语义；这些论断
必须继续跟入 `Bucket.put`、`DiskStorage.persist_bucket` 与对应测试。反过来，在
`storage/` 深处找到 helper，也不能证明调用者能通过受支持 API 使用它。因此每章都
会把公开入口、真正拥有机制的内部函数，以及把结果变成可观察事实的实验配在一起。

## 3. 第一个桶与对象

`src/minis3/store.py` 中的 `MiniS3.create_bucket` 进入存储锁，拒绝重复名称，
创建 `Bucket`，先要求 `DiskStorage.create_bucket` 发布它，随后才加入内存桶映射。
所以桶是所有权和命名边界，不是包含用户可见子目录的目录。

`MiniS3.put_object` 采用相同的“候选状态后发布”形状：

```python
with self._lock:
    candidate = deepcopy(self._bucket(bucket))
    result = candidate.put(key, body, self._counter, now=self._clock())
    self._storage.persist_bucket(candidate)
    self._buckets[bucket] = candidate
    return result
```

这段短代码是全书第一个重要机制。它不先修改活跃 `Bucket`，而是复制它，对副本执行
`Bucket.put`，持久化候选状态，然后替换内存引用。如果持久化抛错，运行进程中的旧桶
仍是权威状态。第 5 章将展示 manifest 如何在重启后给出同样的旧或新边界。

`src/minis3/bucket.py` 中的 `Bucket.put` 复制输入字节，分配公开版本 ID 和唯一内部
存储 ID，计算 ETag，再创建 `src/minis3/model.py` 中冻结的 `Version`。新建且未
启用版本控制的桶使用字面字符串 `"null"` 作为公开版本 ID。这里的 null 是一个真实
公开槽位名，不是 Python 的 `None`。

`MiniS3.get_object` 在同一把锁下查桶，再委托给 `Bucket.get`。未提供
`version_id` 时，它读取最新项；数据项返回 `Version`，key 不存在或最新项是删除
标记时抛出 `NoSuchKey`。

## 4. 动手实验：一次完整往返

在仓库根目录运行以下命令。临时目录让实验可重复，结束后不会留下本地存储。

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minis3 import MiniS3

with TemporaryDirectory() as root:
    store = MiniS3(root)
    store.create_bucket("notes")
    stored = store.put_object("notes", "team/plan.txt", b"ship MiniS3")
    loaded = store.get_object("notes", "team/plan.txt")
    print(stored.version_id)
    print(stored.etag)
    print(loaded.body.decode())
PY
```

实测输出：

```text
null
"174ea9a5b4991a70e5ca3cb0b9805697"
ship MiniS3
```

第一行确认未版本化的 `null` 槽位。第二行是完整 body 的带引号 MD5 指纹，由
`src/minis3/model.py` 的 `content_etag` 产生；它不是认证标签。第三行确认 GET
返回完整字节。key 含有斜杠，但实验没有在对象模型里创建 `team` 目录。第 2 章会
精确定义这一区别。

若要做持久实验，把 `TemporaryDirectory` 换成 `"./minis3-data"` 一类路径。
重新打开 `MiniS3("./minis3-data")` 会调用 `DiskStorage.load_buckets` 重建已发布
状态。只有明确要重置实验时才删除该目录。

## 5. 与 Amazon S3 对照

最接近的真实服务操作是 `CreateBucket`、`PutObject`、`GetObject` 和
`HeadObject`。在语义层面，两套系统都把 PUT 视为替换完整对象值，而不是就地编辑
字节区间。不过 MiniS3 的 `head_object` 只是返回与 GET 相同的本地 `Version`，
其中包括字节；Amazon S3 的 HEAD 是没有对象 body 的 HTTP 响应。

更大的边界在传输和部署。MiniS3 没有 HTTP/XML endpoint、SigV4 签名、IAM、
region、account、bucket policy、加密、storage class、复制、quota 或分布式持久性。
Python 异常代替 HTTP 形态的结果；单进程和一把 `RLock` 代替并发控制；本地 `fsync`
与原子 rename 只承载狭窄的崩溃一致性课程，不代表 Amazon S3 内部实现。

这些差异不能藏在脚注里。仓库在[映射矩阵](../mapping.md)中记录桶、扁平 key、
完整 PUT、ETag 和 manifest 的对应关系，在
[与 Amazon S3 的差异](../DIFFERENCES.md)中列出协议和生产能力缺口。本书中，
“S3 风格”表示某个具名不变量在文档边界内吻合，绝不表示线协议兼容或生产等价。

## 6. 全书地图

后续章节从今天的往返操作向外展开：

1. [对象与 ETag](02-objects-etag.md)区分 key、不可变值、公开版本 ID、存储 ID
   和指纹。
2. [版本化](03-versioning.md)加入不可逆状态机、保留历史和删除标记。
3. [List 与目录幻觉](04-listing.md)从扁平 key 字符串推导目录式视图，并讨论分页。
4. [崩溃原子性](05-crash-atomicity.md)跟踪不可变 artifact、`fsync`、rename、
   manifest 和启动清理。
5. 第 6–8 章加入分片上传、条件 CAS 与确定性生命周期过期。
6. 第 9 章以方法论和仍在微型系统之外的生产能力收束。

## 练习

### 理解题

1. 为什么 `MiniS3.put_object` 在替换活跃内存桶之前，先修改深拷贝？
2. 实测输出中的 `null` 表示什么，又不表示什么？

??? note "参考答案"

    1. 副本让持久化在进程暴露候选状态前完成。持久化失败时，原有内存桶不变。
       第 5 章会补上重启后的另一半推理。
    2. `null` 是未版本化或暂停版本化桶的可替换公开版本 ID。它不表示“没有对象”、
       Python `None` 或缺少持久 artifact。

### 动手题

3. 不修改 `src/`，扩展内联实验：结束第一个 `MiniS3` 实例后，在同一临时根目录上
   打开第二个实例，验证 `team/plan.txt` 仍为 `b"ship MiniS3"`。

   **验收方式：**脚本打印 `recovered: True`，且 `uv run pytest -q` 保持全绿。

??? note "参考答案"

    在临时目录代码块内加入：

    ```python
    reopened = MiniS3(root)
    print(
        "recovered:",
        reopened.get_object("notes", "team/plan.txt").body == b"ship MiniS3",
    )
    ```

    这只是实验代码，不要写入 `src/`。

## 小结

MiniS3 的直接 API 是观察真实存储思想的一扇窄窗：一个门面串行化调用，桶逻辑构造
不可变版本，持久化层先发布候选状态，进程再暴露它。第一次 PUT 返回 `null` 版本和
带引号 ETag，但两者编码的是完全不同的身份。第 2 章将拆开这些身份，并说明为什么
看似路径的对象 key 仍然是扁平的。
