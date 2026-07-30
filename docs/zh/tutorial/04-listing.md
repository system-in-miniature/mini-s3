# 第 4 章：List 与目录幻觉

对象 key 是扁平字符串，但对象存储控制台经常展示文件夹。理解 listing 是一种投影后，
表面矛盾就消失了。请求给出 `prefix`，也可给出 `delimiter`；匹配字符串要么作为
对象返回，要么被分组为推导出的 common prefix。存储对象模型完全没有改变。MiniS3
在 `src/minis3/listing.py` 中实现了整套幻觉。

## 学习目标

完成本章后，你将能够：

- 计算一次 prefix/delimiter 请求的 `contents` 与 `common_prefixes`；
- 解释 common prefix 为什么是查询结果而非存储记录；
- 描述 MiniS3 的字典序与 `max_keys` 计数；
- 解释 continuation token 的查询绑定，以及两页之间发生变更时的限制；
- 区分当前对象列表与完整版本列表，并说明项目的强一致边界。

## 1. Listing 是单个快照上的投影

`src/minis3/store.py` 中的 `MiniS3.list_objects` 持有存储的 `RLock`，把选定桶的
`records` 传给 `listing.list_objects`。这个纯函数基于同一个内存状态构造结果。
PUT、DELETE、版本配置变化与 listing 使用同一把锁，因此本进程中的一次 list 调用
不会在中途与 mutation 交错。

返回类型 `ListObjectsResult` 包含：

- `contents`：当前可见对象；
- `common_prefixes`：推导出的分组名；
- `key_count`：本页 content 与 prefix 的总数；
- `next_token`：不透明 continuation token 或 `None`。

它的 `is_truncated` 属性在且仅在 `next_token` 存在时为真。`ListedObject` 只暴露
当前元数据：精确 key、ETag、size 和 version ID；列表结果不会复制 body。

分组之前，`list_objects` 先应用当前可见性。没有历史的记录被跳过，最新项是
`DeleteMarker` 的记录也被跳过。因此 list 与默认 GET 一致：被 marker 遮住的 key
不是当前对象。

## 2. Prefix 过滤字符串

函数对每条记录先检查：

```python
if not key.startswith(prefix) or not record.versions:
    continue
```

prefix 是字面字符串谓词。`photos/` 没有持久目录含义；它只选择开头字符匹配的 key。
空 prefix 选择全部当前对象。

假设存储包含：

```text
photos/2025/a.jpg
photos/2026/b.jpg
photos/readme.txt
```

使用 `prefix="photos/"` 且无 delimiter，三个精确 key 都是 contents。使用
`prefix="photos/2025/"`，只有第一个匹配。过程中没有树遍历。

## 3. Delimiter 生成 Common Prefix

从匹配 key 中去掉 prefix 后，`list_objects` 在剩余 suffix 中查找 delimiter：

```python
suffix = key[len(prefix):]
if delimiter is not None and delimiter in suffix:
    boundary = suffix.index(delimiter) + len(delimiter)
    prefixes.add(prefix + suffix[:boundary])
else:
    contents[key] = ListedObject(...)
```

只看请求 prefix 之后的第一个 delimiter。空 prefix 加 `/` delimiter 时，三个示例
key 都贡献相同的 `photos/`，再由 set 去重。使用 prefix `photos/` 与 `/` 时，
两个年份 key 分别贡献 `photos/2025/` 与 `photos/2026/`；
`photos/readme.txt` 的剩余部分没有斜杠，因此作为 content 返回。

所以只要改变请求，同一个存储 key 就可以被直接返回、归入 common prefix，或根本不
匹配。这也说明不需要创建以 `/` 结尾的零字节 key 才能分组。应用可以自行创建这类
“folder marker”对象，但它们仍是普通对象，不是目录；MiniS3 不特殊处理它们。

空字符串 delimiter 无法定义有意义的第一边界，因此被拒绝。MiniS3 接受任何非空
字符串，不过 `/` 是传统 S3 delimiter。

## 4. 排序、页大小与 Token

MiniS3 为 contents 和 common prefixes 构造 `(name, kind)` 组合列表，再执行
`combined.sort()`。因此名称按字典序排列，content 与 common prefix 共享
`max_keys` 预算；`key_count` 是组合页长度，不只是对象数。

分页使用该已排序组合投影的 offset。`_encode_token` 把 offset、prefix 和 delimiter
序列化为紧凑 JSON，再用去掉 padding 的 URL-safe base64 编码。`_decode_token`
恢复 padding，解析 JSON，并验证 prefix 与 delimiter 和当前请求相同。畸形 token、
负数或非整数 offset，以及来自不同查询的 token 都抛出
`InvalidContinuationToken`。

“不透明”表示调用者应原样回传 token，而不是依赖其表示推导含义；不表示它加密或
签名。MiniS3 的 token 刻意保持简单且本地。

请求之间也没有固定快照。每次分页调用都观察一个强一致当前状态，但第一页和第二页
之间的变更可能改变组合序列相对于已保存 offset 的位置，某个条目可能跨越边界。
[与 Amazon S3 的差异](../DIFFERENCES.md)明确说明这一点，所以不能把“每次调用
一致”夸大为“多页快照保证”。

实现还暴露了这个教学设计的成本模型。`list_objects` 每次请求都会扫描所有 record，
构建 dictionary 与 set，组合投影名称，再排序。工作量大致是 record 线性扫描加
匹配结果排序，而不是有索引的 prefix 查询。这份简洁性让排序和分组容易检查，却不是
生产扩展性声明。分布式对象存储需要分区感知索引与 continuation 状态，不能从这个
内存投影直接推断其设计。

切片语义还带来一个边界：`max_keys=0` 返回空页；若结果非空，则返回 offset 为零的
continuation token。负值会被拒绝。

## 5. 当前对象与版本

`list_object_versions` 是另一个函数，使用不同结果类型。它排序 key，再按最新在前
发出每个数据版本和 delete marker，并把每个历史第一项标成 latest。它接受 prefix，
但没有 delimiter 分组或分页。

两个 API 回答不同问题：

- `list_objects`：“目前哪些完整对象可见，并可选择为导航进行分组？”
- `list_object_versions`：“保留了哪些历史项，包括 marker？”

把两者合并，要么会把隐藏历史泄漏进普通导航，要么会丢掉版本恢复所需信息。

## 6. 动手实验：只改变投影

运行：

```bash
uv run python labs/lab_directory_illusion.py
```

实测输出：

```text
Stored exactly these flat keys: ['photos/2025/a.jpg', 'photos/2026/b.jpg', 'photos/readme.txt']
prefix='', delimiter=None
  contents: ['photos/2025/a.jpg', 'photos/2026/b.jpg', 'photos/readme.txt']
  common prefixes: []
prefix='', delimiter='/'
  contents: []
  common prefixes: ['photos/']
prefix='photos/', delimiter='/'
  contents: ['photos/readme.txt']
  common prefixes: ['photos/2025/', 'photos/2026/']
No directory record was created; only the list projection changed.
```

lab 在不变状态上执行三次读取。因而因果结论很强：只有请求参数改变，所以目录形输出
必然是推导结果。`tests/test_listing.py` 还检查分页、查询绑定 token、marker 遮挡和
版本扁平化。

## 7. 一致性与真实 S3 对照

MiniS3 的当前列表和版本列表在单进程内强一致，因为每个公开调用共享同一把锁，列表
计算读取当前内存桶。完成的 mutation 会安装新候选状态；它之前的 list 看到旧状态，
之后的 list 看到新状态。

现代 Amazon S3 对对象 PUT、DELETE 和 list 操作也提供强 read-after-write 一致性。
历史上 S3 list 曾是最终一致；AWS 在 2020 年 12 月宣布强一致。仅仅因为“S3 listing
最终一致”就规定等待或 reconciliation 的设计解释，对现代 general-purpose S3 已
过时；当然应用缓存或其他外围系统仍可能引入自己的陈旧性。

prefix/delimiter 分组不变量在本项目边界内等价，见
[映射矩阵](../mapping.md)。MiniS3 分页是刻意简化：token 无签名、本地且基于 offset，
不模拟分布式 continuation 机制。版本列表省略 S3 key marker、version-ID marker、
分页字段、owner、时间格式与 encoding 选项。详见
[与 Amazon S3 的差异](../DIFFERENCES.md)中的 listing 与 version-listing 条目。

## 练习

### 理解题

1. 已有 key `a/1`、`a/2/x` 与 `b` 时，`prefix="a/"`、`delimiter="/"` 的
   contents 与 common prefixes 是什么？
2. 为什么两个各自强一致的分页请求仍可能无法代表同一个稳定多页快照？

??? note "参考答案"

    1. Contents 为 `["a/1"]`，common prefixes 为 `["a/2/"]`。查找下一 delimiter
       前会先去掉 prefix。
    2. 锁保护每次调用，不保护调用间隔。第二次请求按保存 offset 解释序列前，mutation
       可以改变字典序位置。

### 动手题

3. 写内联脚本，插入 `a.txt`、`dir/x`、`z.txt`，使用 `delimiter="/"`、
   `max_keys=2` 获取两页，再合并它们。

   **验收方式：**合并名称恰为 `{"a.txt", "dir/", "z.txt"}`；第一页 token 非
   `None`；第二页 `next_token is None`。

??? note "参考答案"

    ```python
    first = store.list_objects("b", delimiter="/", max_keys=2)
    second = store.list_objects(
        "b",
        delimiter="/",
        max_keys=2,
        continuation_token=first.next_token,
    )
    names = {
        *(x.key for x in first.contents),
        *first.common_prefixes,
        *(x.key for x in second.contents),
        *second.common_prefixes,
    }
    assert names == {"a.txt", "dir/", "z.txt"}
    assert first.next_token is not None
    assert second.next_token is None
    ```

4. 提出但不要应用一个 token 查询绑定测试。

   **验收方式：**先用一个 prefix 或 delimiter 获取 token，再用于不同查询，预期
   `InvalidContinuationToken`，且不修改 `src/`。

??? note "参考答案"

    ```diff
    +store = _populated_store(tmp_path)
    +first = store.list_objects("b", max_keys=1)
    +assert first.next_token is not None
    +with pytest.raises(InvalidContinuationToken):
    +    store.list_objects(
    +        "b", prefix="different", continuation_token=first.next_token
    +    )
    ```

    第一次无 prefix 请求有多个结果，因此 `max_keys=1` 必然生成真实
    token。随后用非空 prefix 重用该 token，才会真正进入 query binding
    校验，而不是把 `None` 传回去。

    `tests/test_listing.py::test_malformed_or_query_mismatched_tokens_are_rejected`
    已提供这条契约。

## 小结

Listing 不会发现目录，而是从当前扁平 key 计算确定性投影。Prefix 过滤，delimiter
分组，分页则切分一个按字典序排列的对象与 common prefix 组合。MiniS3 内每次调用
强一致，但 continuation token 不固定跨调用状态。第 5 章将沿一次 mutation 深入这
个读取投影之下，找出崩溃后让新状态可见的文件系统事件。
