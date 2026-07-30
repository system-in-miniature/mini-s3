# 08 — 生命周期过期

## 学习目标

学完本章，你能够：

- 把纯生命周期选择与持久变更分开；
- 解释 prefix 过滤、年龄阈值及边界包含行为；
- 区分当前与非当前版本过期；
- 预测版本化如何改变当前对象过期的结果；
- 说明 MiniS3 手动确定性 tick 与 Amazon S3 生命周期的差异。

## 机制讲解：先决策，再应用

对象存储会积累数据，生命周期规则用年龄表达保留策略。MiniS3 只实现过期，但借此展示一个重要设计：策略选择应在修改存储前保持确定、可检查。

`src/minis3/lifecycle.py::ExpirationRule` 包含稳定的规则 ID、key prefix，以及可选的当前/非当前阈值。`__post_init__` 拒绝没有阈值或含负年龄的规则；0 合法，表示在求值时刻立即满足。

规则是传给 tick 的值，不是桶的持久配置，也不读取时钟。`src/minis3/lifecycle.py::_old_enough` 接受全部输入：

```python
return threshold is not None and now - created_at >= threshold
```

`>=` 表示包含边界：创建于 0、阈值 10 的版本在恰好 10 时就会被选中。注入 `now` 避免不稳定 sleep，并使边界可测试。

`src/minis3/lifecycle.py::evaluate_expiration` 接受记录快照、规则和显式 `now`，返回不可变 `LifecycleAction` 元组而不修改记录。key 按排序遍历，规则只在 `key.startswith(rule.prefix)` 时适用。

每条记录的 `versions[0]` 是当前项。只有它是 `src/minis3/model.py::Version` 才考虑当前过期，`DeleteMarker` 不会入选。`versions[1:]` 中的数据版本才考虑非当前过期；MiniS3 不过期删除标记。

动作携带 `rule_id`、key、精确 version ID 和 `EXPIRE_CURRENT`/`EXPIRE_NONCURRENT`。`selected` 集合会对相同 key、版本和动作种类去重；重叠规则中先出现的规则提供报告 ID。因此固定快照、规则顺序和时间会产生固定结果。

返回动作而非立刻删除，让纯选择阶段可脱离磁盘和时间单测，也分开了职责：选择回答策略问题，服务负责同步、版本状态转换和持久发布。

`src/minis3/store.py::MiniS3.lifecycle_tick` 负责第二阶段。它获取 `RLock`，深拷贝桶，只采样一次注入时钟，再对候选调用 `evaluate_expiration`，所以一次 tick 中所有规则看到同一时刻与稳定视图。

对 `EXPIRE_NONCURRENT`，服务以精确 version ID 调用 `src/minis3/bucket.py::Bucket.delete`，物理移除历史项。对 `EXPIRE_CURRENT`，先确认选中版本仍为当前，再无 version ID 调用删除。

后者会遵循版本化状态机：启用桶中的当前删除会新建 `DeleteMarker`，旧字节被隐藏但仍保留，直到非当前规则移除；未版本化桶物理删除 `null` 版本；暂停桶遵循第 3 章所述的暂停/null 规则。生命周期不会绕过 `Bucket`。

动作全部应用到候选后，tick 只调用一次 `src/minis3/storage/disk.py::DiskStorage.persist_bucket`，再替换内存桶。因此整组动作是一次本地桶发布，而不是一串部分可见删除；无动作时不写 manifest。

创建时间同样来自注入时钟。`MiniS3.put_object` 与 multipart 完成都向 `Bucket.put` 传 `self._clock()`；`DiskStorage._write_artifact` 持久化 `created_at`，`_load_artifact` 恢复它，所以重启不会重置年龄。

有两个必须诚实说明的差异。第一，MiniS3 从版本最初创建时计算非当前年龄；Amazon S3 的 `NoncurrentDays` 从版本变成非当前时开始，而 MiniS3 未持久化该转换时间。第二，没有后台自动执行；若应用不调用 `lifecycle_tick`，超龄版本可以一直存在。

### 重叠规则与重复 tick

规则可重叠，如 `logs/` 与 `logs/audit/`。求值按调用者顺序遍历，但对同一 key/版本/动作去重，动作报告第一个选中它的规则。由于当前只有过期这一动作族，MiniS3 不建模生产系统中不同动作类型的冲突消解。

重复 tick 由状态自然保证。非当前版本移除后不再出现在下一快照；当前过期创建删除标记后，该标记不是 `Version`，不会反复堆叠当前过期标记。其后的旧数据处于历史位置，可在未来被非当前规则选中。这无需单独的“规则已执行”数据库。

`lifecycle_tick` 只有在持久化成功后才返回动作；若存储抛错，调用者不能因为纯求值本可选中就记录完成。真正后台执行还需要重试状态、指标、限速和崩溃安全的任务归属，手动同步 API 没有冒充这些能力。

## 对照真实 Amazon S3

真实 S3 把规则持久在桶上，由托管后台服务执行；过滤可含 prefix、标签、大小及组合，动作还包括当前/非当前过期、删除标记清理、放弃 multipart 上传、存储类别转换。执行时间由服务管理，不保证恰在边界瞬间发生。

MiniS3 只有数据版本的 prefix+年龄过期，手动 tick 在单进程内同步、确定、原子。它没有调度器、持久规则、标签、大小过滤、类别转换、费用/最短保存期、删除标记清理或未完成上传过期，也不建模 S3 日期取整和 HTTP Last-Modified。

可比范围是：启用版本化时当前过期创建删除标记，非当前过期移除指定历史版本，未版本化当前过期移除对象。[mapping 的 Expiration tick 行](../mapping.md) 将其列为有意简化；[DIFFERENCES 的 Lifecycle 与 Time](../DIFFERENCES.md) 记录非当前计龄和手动调度差异。

## 动手实验

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minis3 import ExpirationRule, MiniS3, NoSuchKey
class Clock:
    now = 0.0
    def __call__(self): return self.now
with TemporaryDirectory() as root:
    clock = Clock()
    store = MiniS3(root, clock=clock)
    store.create_bucket("demo")
    store.set_bucket_versioning("demo", "enabled")
    store.put_object("demo", "logs/app.log", b"old")
    clock.now = 5
    store.put_object("demo", "logs/app.log", b"current")
    rule = ExpirationRule("logs", prefix="logs/",
        expire_current_after=10, expire_noncurrent_after=12)
    clock.now = 12
    print([(a.kind.value, a.version_id) for a in store.lifecycle_tick("demo", [rule])])
    clock.now = 15
    print([(a.kind.value, a.version_id) for a in store.lifecycle_tick("demo", [rule])])
    try: store.get_object("demo", "logs/app.log")
    except NoSuchKey: print("current GET: NoSuchKey")
    print([(v.version_id, v.is_delete_marker)
           for v in store.list_object_versions("demo").versions])
PY
```

本仓实测输出：

```text
[('expire_noncurrent', 'v00000001')]
[('expire_current', 'v00000002')]
current GET: NoSuchKey
[('v00000003', True), ('v00000002', False)]
```

时间 12 时旧版本年龄为 12，被作为非当前项移除；当前版本仅 7。时间 15 时当前版本恰达阈值 10，过期创建标记 `v00000003`，普通 GET 失败而 `v00000002` 仍可按 ID 访问。

```bash
uv run pytest -q tests/test_lifecycle.py
```

## 练习

1. **理解题。** 为什么 `evaluate_expiration` 接收 `now` 而不调用 `time.time()`？

??? note "参考答案"
    显式输入使决策纯粹、确定，并能精确测试边界。tick 只采样一次时钟；隐藏读时钟可能在遍历中变化并迫使测试 sleep。

2. **理解题。** 为什么启用桶的当前过期创建标记，而非当前过期物理删除？

??? note "参考答案"
    当前过期使用桶的普通无地址删除，按版本语义新增标记；非当前动作已经指定历史 version ID，所以删除精确条目。

3. **动手题。** 把实验复制到 `/tmp/lifecycle-boundary.py`，分别在 `14.999` 与 `15` tick。

    验收：前者当前过期动作为空，后者恰有一个 `expire_current`。

??? note "参考答案"
    当前版本创建于 5、阈值为 10；`>=` 解释了边界转换。不要修改 `src/`。

4. **动手题。** 向 `/tmp` 脚本加入 `keep/` 对象，同时保留 `logs/` 规则。

    验收：两次 tick 后 `keep/item` body 仍存在，任何动作都不含该 key。

??? note "参考答案"
    推进时钟前 PUT `keep/item`，打印动作 key 与存活 body。prefix 不匹配时，年龄无关。

## 小结

MiniS3 生命周期是两阶段策略引擎：纯、确定的选择产生显式动作，一次加锁服务操作再通过普通版本化与持久化机制应用它们。最终章会用同一方法——小机制、可执行契约、清晰边界——说明如何继续走向真实对象存储。
