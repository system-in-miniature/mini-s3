# 第 2 章：对象、扁平 Key 与 ETag

把熟悉的文件系统词汇悄悄带入对象存储，最容易产生误解。`photos/2026/cat.jpg`
看起来像路径，ETag 看起来像校验和，PUT 看起来像覆盖文件。每个类比都有一部分
有用、一部分危险。本章用 MiniS3 的具体值模型替代这些类比。

## 学习目标

完成本章后，你将能够：

- 解释 MiniS3 命名空间为什么是从不透明 key 字符串到 `ObjectRecord` 历史的映射；
- 区分对象值、`Version`、`ObjectRecord`、公开 `version_id` 和内部 `storage_id`；
- 使用 `content_etag` 推导单次 PUT 的 ETag，并说明它在真实 S3 中为什么不是通用
  内容身份；
- 解释完整对象替换与不可变性，而不把它们误解为 Python 变量不可变；
- 通过直接 API 验证扁平 key 和替换行为。

## 1. 值模型

权威定义位于 `src/minis3/model.py`。`ObjectRecord` 是冻结 dataclass，只有一个
精确 `key` 和一个最新在前的版本 tuple：

```python
@dataclass(frozen=True, slots=True)
class ObjectRecord:
    key: str
    versions: tuple[ObjectVersion, ...] = ()
```

key 不会被切分、规范化或解释。因此 `/a//b/`、`a/b` 和 `a//b` 是三个不同 key。
不存在 `a` 的 inode、名为 `b` 的子项或目录遍历。之后
`src/minis3/listing.py` 的 `list_objects` 可以围绕 delimiter 对字符串分组，但
那是查询投影，不是持久层级。

`Version` 表示一个完整数据值：

```python
@dataclass(frozen=True, slots=True)
class Version:
    version_id: str
    storage_id: str
    sequence: int
    body: bytes
    etag: str
    created_at: float = 0.0
    multipart_upload_id: str | None = None
```

dataclass 被冻结，调用者不能给返回的 `Version` 重新赋 body 或 ETag。更重要的是，
存储设计把每个版本视为不可变 artifact。更新会创建另一个 `Version`，不会就地编辑
旧值。旧版本是否继续公开保留取决于桶的版本控制状态，第 3 章会讨论。

`DeleteMarker` 是 `ObjectVersion` union 的另一个成员。它有身份与创建时间，但没有
body 或 ETag。它成为最新历史项，遮住更早数据。让数据和 marker 使用不同类型，使
无效状态更难表达：代码无法误读 `marker.body`。

## 2. 公开身份与存储身份

`src/minis3/bucket.py` 的 `Bucket.put` 获取一个 sequence，再从中生成两个 ID。
`version_id` 是公开对象历史身份；`storage_id` 始终是 `e00000001` 这类唯一字符串，
用于命名不可变磁盘 artifact。

为什么需要两者？未版本化桶的每次可见 PUT 都使用公开版本 ID `"null"`；暂停版本化
的桶也会反复替换公开 null 槽位。如果把 `"null"` 当作磁盘文件名，就需要破坏性的
就地覆盖，削弱发布协议。新 `storage_id` 让 MiniS3 先写新 artifact，待其持久化后
才切换 manifest。公开语义可以说“替换 null 槽”，而存储机制仍坚持“不覆盖已发布
版本 artifact”。

`sequence` 单独保存，因为排序和恢复需要数值事实，而公开与存储 ID 是格式化字符串。
`src/minis3/bucket.py` 的默认 `SequenceCounter` 是确定性的。启动时，
`MiniS3.__init__` 从 `DiskStorage.load_buckets` 取得已恢复的最大 sequence，再把
counter 推进到它之后。真实 S3 版本 ID 是服务生成的不透明值；MiniS3 可读 ID 是测试
简化，不是兼容承诺。

## 3. 完整对象替换

`Bucket.put` 从 `body=bytes(body)` 开始。即使调用者传入其他 bytes-like 对象，这一
转换也会捕获一个字节值。随后计算 ETag，构造新的冻结 `Version`。

对未版本化或暂停版本化的桶，函数删除公开 ID 为 `"null"` 的旧项，保留具名项，再把
新值放在最前。对已启用版本控制的桶，它把新值放在最前并保留所有旧项。两条分支都
完整替换**当前对象值**。MiniS3 不提供字节区间变更、append 或 patch。

这不意味着 Python `Bucket` 聚合不可变。`Bucket.records` 是可变字典，
`Bucket.put` 会替换其中的 `ObjectRecord`。不可变性属于已发布值对象和磁盘
artifact。服务通过 `MiniS3.put_object` 在锁内复制桶、持久化候选状态，再安装它，
从而安全协调聚合变更。

`MiniS3.get_object` 返回保存的 `Version` 值。`head_object` 调用 `get_object`，
所以也返回同一值，包括本地 body 字节。这适合直接教学 API，却不同于 HTTP HEAD。

## 4. ETag 表达什么

普通 PUT 中，`Bucket.put` 调用 `src/minis3/model.py` 的 `content_etag`：

```python
def content_etag(body: bytes) -> str:
    digest = md5(body, usedforsecurity=False).hexdigest()
    return f'"{digest}"'
```

有三点要注意。第一，输入是完整 body；通过这条单次 PUT 路径写入的相同字节会得到
相同 ETag。第二，十六进制摘要带引号，因为 S3 HTTP ETag 是带引号的 entity tag。
第三，`usedforsecurity=False` 记录了它的角色：MD5 在此是熟悉的指纹，不是安全
签名。ETag 不认证写入者，也不抵御恶意碰撞。

分片完成的规则不同。MiniS3 会对各 part 的**二进制 MD5 摘要拼接结果**再哈希，并
附加 part 数。因此同样的最终字节可以因 part 边界不同而获得不同 ETag。第 6 章将
展开这一机制。即便不考虑 multipart，真实 S3 ETag 也并非总是 MD5，因为加密和
服务选择会改变含义。除非明确保证更窄契约，代码应把 ETag 当作不透明 validator。

## 5. 动手实验：路径形 key 与替换

运行：

```bash
uv run python - <<'PY'
from dataclasses import FrozenInstanceError
from tempfile import TemporaryDirectory
from minis3 import MiniS3, content_etag

print(content_etag(b"hello"))
with TemporaryDirectory() as root:
    store = MiniS3(root)
    store.create_bucket("objects")
    first = store.put_object("objects", "/a//b/", b"hello")
    second = store.put_object("objects", "/a//b/", b"HELLO")
    print(first.version_id, second.version_id)
    print(store.get_object("objects", "/a//b/").body)
    print([item.key for item in store.list_objects("objects").contents])
    try:
        second.etag = "changed"
    except FrozenInstanceError:
        print("Version is frozen")
PY
```

实测输出：

```text
"5d41402abc4b2a76b9719d911017c592"
null null
b'HELLO'
['/a//b/']
Version is frozen
```

列表包含精确的路径形字符串，而不是重建路径。版本控制尚未启用，所以两次 PUT 都
使用同一公开 null 槽；GET 只返回替换后的 body。局部变量 `first` 仍引用旧冻结值，
但它已不在桶的公开历史中。freeze 错误验证值对象不可变，观察到的替换验证聚合可变。

## 6. 与 Amazon S3 对照

Amazon S3 同样使用扁平对象 key 命名空间，PUT 也替换完整对象值。斜杠只因客户端与
控制台使用 prefix 和 delimiter 才具有约定含义。这个不变量在
[映射矩阵](../mapping.md)中标为 **Equivalent**。

MiniS3 在多处缩窄了模型：

- body 位于本地文件，也会载入 `Version.body`；它不流式处理 TB 级对象；
- 单次 PUT ETag 永远是带引号的完整 body MD5，而真实 S3 ETag 并非总是内容 MD5；
- ID 确定且可读，而非不透明；
- `head_object` 因没有 HTTP 响应层而返回 body；
- 元数据由一个本地进程拥有，不是分布式服务。

精确的 ETag、HEAD、时间和并发差异见
[与 Amazon S3 的差异](../DIFFERENCES.md)。有效的比较不是“实现相同”，而是
“在更小的执行与持久化边界内保持同一个具名对象不变量”。

## 练习

### 理解题

1. 多次写入的公开 `version_id` 都可能是 `"null"` 时，为什么仍需要唯一
   `storage_id`？
2. 冻结的 `Version` 是否让整个存储不可变？请分开解释两个层级。

??? note "参考答案"

    1. 存储 ID 为每次写入命名新的不可变 artifact。即使公开状态机把两个值都叫
       `null`，manifest 仍可在 artifact 之间原子切换。
    2. 不是。`Version` 值不可修改，但 `Bucket.records` 是可变聚合，在存储锁下
       替换条目。更新会创建新的不可变值并安装新 record。

### 动手题

3. 不修改 `src/`，写一个内联脚本，同时存储 `a/b` 和 `a//b`，证明列表中有两个
   精确 key，且它们返回不同 body。

   **验收方式：**排序后的 key 等于 `["a//b", "a/b"]`，两个 GET 断言均通过，
   且 `uv run pytest -q` 保持全绿。

??? note "参考答案"

    ```python
    with TemporaryDirectory() as root:
        store = MiniS3(root)
        store.create_bucket("b")
        store.put_object("b", "a/b", b"one")
        store.put_object("b", "a//b", b"two")
        keys = sorted(item.key for item in store.list_objects("b").contents)
        assert keys == ["a//b", "a/b"]
        assert store.get_object("b", "a/b").body == b"one"
        assert store.get_object("b", "a//b").body == b"two"
        print(keys)
    ```

4. 设计但不要应用一个为 `Version` 增加 `sha256` 元数据字段的 patch。指出所有需要
   变化的构造、持久化、恢复和测试位置。

   **验收方式：**答案至少包含 `model.Version`、`Bucket.put`、
   `DiskStorage._write_artifact`、`DiskStorage._load_artifact` 和一个 model 或
   storage 测试；不修改任何 `src/` 文件。

??? note "参考答案"

    正确计划应在 `src/minis3/model.py` 添加冻结字段，在 `Bucket.put` 构造版本时
    计算它，在 `DiskStorage._write_artifact` 序列化，在
    `DiskStorage._load_artifact` 校验并重建，同时更新直接 `Version(...)` 构造和
    round-trip 测试。还应决定如何处理缺少该字段的旧 manifest。这只是设计题。

## 小结

MiniS3 保存精确 key 字符串，以及一个最新在前的不可变值 tuple。公开版本身份与内部
存储身份刻意分离，让公开 null 槽可以被替换而无需覆盖已发布 artifact。单次 PUT
ETag 是此教学路径中的带引号 MD5 指纹，不是通用或安全身份。第 3 章将把单槽历史
扩展成显式版本控制状态机。
