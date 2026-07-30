# 第 3 章：版本化、删除标记与 Null 槽

版本控制会改变 PUT 和 DELETE 的含义。启用前，对象只有一个可替换的公开 `null`
槽。启用后，每次 PUT 都添加具名值，普通 DELETE 添加 marker 而不是销毁历史。
暂停版本控制也不会回到原来的世界：具名历史继续存在，新写入则重新使用可替换 null
槽。MiniS3 把这些规则编码成一个小状态机，其完整行为都在
`src/minis3/bucket.py` 中。

## 学习目标

完成本章后，你将能够：

- 画出 `UNVERSIONED`、`ENABLED` 与 `SUSPENDED` 之间的合法转换；
- 预测每种状态下 PUT 与 DELETE 的行为；
- 解释 delete marker 如何遮住字节而不删除旧版本；
- 区分当前 GET/DELETE 与按版本 GET/DELETE；
- 检查扁平版本列表，并恢复被遮住的历史值。

## 1. 状态机

`src/minis3/bucket.py` 中的 `VersioningState` 定义三种状态：

```python
class VersioningState(StrEnum):
    UNVERSIONED = "unversioned"
    ENABLED = "enabled"
    SUSPENDED = "suspended"
```

每个新 `Bucket` 都从未版本化开始。`Bucket.set_versioning` 把字符串或 enum 输入转换
成状态，再执行两条护栏：离开 `UNVERSIONED` 后，任何回到该状态的转换都被拒绝；
直接 `UNVERSIONED -> SUSPENDED` 也被拒绝。有效转换图为：

```text
UNVERSIONED ──enable──> ENABLED <──resume── SUSPENDED
                            └──suspend──>───┘
```

自转换允许存在。缺失的箭头与存在的箭头同样重要。“暂停”只停止创建新具名版本，
不会抹去曾启用版本控制这一事实，也不会丢弃具名历史。

`src/minis3/store.py` 中的 `MiniS3.set_bucket_versioning` 在深拷贝上执行转换，持久化
候选桶，再替换到活跃映射。因此版本配置与对象历史共享同一 manifest 发布边界。

## 2. 各状态下的 PUT

`Bucket.put` 获取新 sequence，再选择公开 ID：

```python
version_id = (
    f"v{sequence:08d}"
    if self.versioning is VersioningState.ENABLED
    else NULL_VERSION_ID
)
```

在 `ENABLED` 中，新 `Version` 被放到所有旧版本之前。每次 PUT 获得
`v00000002` 一类具名 ID，所以每个旧值仍可寻址。

在 `UNVERSIONED` 和 `SUSPENDED` 中，函数删除公开 ID 为 `"null"` 的旧项，保留
具名项，再把新 null 值放到最前。对从未版本化的桶，没有具名项，因此像单槽替换。
对暂停状态则是：

```text
before: [null-old, v00000007, v00000003]
PUT:    [null-new, v00000007, v00000003]
```

具名历史继续存在。每个 null 值仍获得唯一内部 `storage_id`，所以崩溃原子发布不需要
覆盖不可变 artifact。

## 3. 当前 GET 与按版本 GET

`Bucket.get` 先找 `ObjectRecord`。未给 `version_id` 时读取第一项。若它是
`Version`，GET 返回它；若是 `DeleteMarker`，即使旧数据仍存在，也抛出
`NoSuchKey`。

给出 `version_id` 时，`Bucket.get` 扫描历史寻找精确公开 ID。数据版本被返回，
marker 产生 `NoSuchKey`，不存在的 ID 产生 `NoSuchVersion`。这让调用方区分
“请求的历史项不存在”和“该项存在但表示删除”，不过 MiniS3 用 Python 异常表达，
而非 HTTP header 和 XML。

marker 遮住当前对象后，精确 ID 路径尤其重要。默认 GET 按设计表现为不存在，
`get_object(..., version_id=old.version_id)` 仍能取得保留字节。

## 4. DELETE 取决于状态

`Bucket.delete` 有两种模式。

提供 `version_id` 时，它只删除匹配的历史项。若还有其他项，其相对顺序不变。若删除
的是最新 marker，下一条数据版本可能重新成为当前值。这是物理编辑历史，不会创建
另一个 marker。

未提供 `version_id` 时，行为取决于状态和历史：

- 真正未版本化且无具名历史的桶会移除 record，返回 `None`；
- 已启用桶会创建具名 `DeleteMarker`，放在最前并保留所有旧项；
- 暂停桶会创建 null marker，替换现有 null 项并保留具名历史。

防御性的 `has_named_history` 分支同样重要。即使公开转换通常不会让未版本化桶拥有
具名历史，如果聚合以异常状态构造或恢复，这条分支也能避免销毁保留值。

`src/minis3/model.py` 的 `DeleteMarker` 包含 `version_id`、`storage_id`、
`sequence` 和 `created_at`，但没有字节与 ETag。类型边界匹配语义角色：它是最新
状态为删除的证据，不是零字节对象。

分析失败或删除语义时，一个好方法是追问：操作改变了可见性、保留性，还是两者。
已启用桶的普通 DELETE 改变可见性，却保留旧数据；删除精确历史数据版本改变保留性，
但可能不改变当前可见性；删除最新 marker 会同时改变两者——它移除一个保留项，并
显露下一项；未版本化 DELETE 则同时移除唯一保留值和可见性。这套词汇能避免把每次
成功 DELETE 都误解成物理字节回收。

## 5. 列出被遮住的历史

`MiniS3.list_object_versions` 委托给 `src/minis3/listing.py` 的
`list_object_versions`。该函数排序 key，遍历每个最新在前的历史，并为数据和 marker
都生成 `ListedVersion`。每个 key 的第一项 `is_latest=True`；marker 的
`is_delete_marker=True`，且 `etag=None`、`size=None`。

当前列表不同。`list_objects` 只看第一项，第一项为 marker 时跳过该 key。于是三个
观察相互一致：

- 当前 GET 给出 `NoSuchKey`；
- 当前对象列表省略 key；
- 版本列表仍显示 marker 与保留值。

## 6. 动手实验：删除但不销毁

运行仓库 lab：

```bash
uv run python labs/lab_versioning.py
```

实测输出：

```text
PUT #1: v00000001 "fedfffb4f154e91a1b00720d80b11387"
PUT #2: v00000002 "564db7a8cce2a309bfdbc66876844f21"
DELETE created marker: v00000003
GET without version-id: NoSuchKey (latest entry is a marker)
Retained history, newest first:
  v00000003: delete-marker, is_latest=true
  v00000002: data, is_latest=false
  v00000001: data, is_latest=false
GET the 'deleted' first version: draft one
```

counter 从一开始，确定 ID 直接暴露操作顺序。DELETE 消耗第三个 sequence 并发布
marker。当前查询失败，但最后的按版本 GET 证明第一个 body 仍存在。这份输出不只是
打印故事：`tests/test_versioning.py` 还包含穷举转换表，以及 null 替换、marker
遮挡、暂停行为和精确版本删除的契约。

## 7. 与 Amazon S3 对照

核心版本转换与 Amazon S3 general-purpose bucket 对齐：一旦启用版本控制，可以
暂停，但不能回到从未启用状态。已启用桶的普通删除创建 delete marker，带
`versionId` 的请求寻址一个保留项；暂停后，可替换 null 版本可与具名历史共存。
这些条目在[映射矩阵](../mapping.md)中有分类。

MiniS3 刻意缩小外围系统：

- 版本 ID 是可读 counter 值，而 S3 ID 不透明；
- 一把锁串行化调用，没有分布式元数据并发；
- 版本列表把所有条目放在一个扁平结果里，省略 S3 分页 marker、owner、时间格式与
  encoding 选项；
- 异常代替 HTTP status、delete-marker header 和 XML body；
- 没有 object lock、retention policy、legal hold、复制或 IAM。

详见[与 Amazon S3 的差异](../DIFFERENCES.md)中的版本 ID、版本列表、错误、
bucket surface 和并发条目。MiniS3 保留状态机课程，不保留完整服务面。

## 练习

### 理解题

1. 即使应用不再需要新具名版本，为什么仍禁止 `SUSPENDED -> UNVERSIONED`？
2. 按精确版本 ID 删除最新 marker 后，可观察状态如何变化？

??? note "参考答案"

    1. 暂停不会抹掉具名历史或桶已有版本语义这一事实。回到“从未版本化”会让保留
       版本与 null 槽含义变得含糊。支持的控制是暂停，它保留历史。
    2. marker 被物理移出历史。若下一项是数据版本，它重新成为当前值；默认 GET 和
       当前列表会再次显示该旧值。

### 动手题

3. 在副本或内联脚本中扩展 lab：保存返回的 marker，使用
   `version_id=marker.version_id` 删除它，再打印当前 body。

   **验收方式：**默认 GET 打印 `draft two`；版本列表包含两个数据版本且没有
   marker；不修改 `src/`。

??? note "参考答案"

    ```python
    store.delete_object(
        "demo", "report.txt", version_id=marker.version_id
    )
    print(store.get_object("demo", "report.txt").body.decode())
    assert all(
        not item.is_delete_marker
        for item in store.list_object_versions("demo").versions
    )
    ```

4. 给出但不要应用一个测试 diff，覆盖从未版本化直接转换到暂停的非法路径。

   **验收方式：**提案使用 `pytest.raises(ValueError)`，检查状态仍为
   `UNVERSIONED`，并指出目标文件是 `tests/test_versioning.py`。

??? note "参考答案"

    ```diff
    +def test_cannot_suspend_before_enabling() -> None:
    +    bucket = Bucket("b")
    +    with pytest.raises(ValueError):
    +        bucket.set_versioning("suspended")
    +    assert bucket.versioning is VersioningState.UNVERSIONED
    ```

    现有参数化转换测试已覆盖该情况；此提案适合作为聚焦练习，但不应实际应用。

## 小结

MiniS3 把版本控制做成显式、不可逆的状态转换。Enabled PUT 保留具名值；暂停只替换
null 槽；普通版本化 DELETE 发布 marker；精确版本操作只编辑一个历史项。因此对象
可在当前视图中不存在，却仍能从历史恢复。第 4 章将从一个 key 的历史转向多个扁平
key 的投影，并解释目录幻觉从何而来。
