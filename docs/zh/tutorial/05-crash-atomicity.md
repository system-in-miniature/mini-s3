# 第 5 章：崩溃原子性与 Manifest 发布

正常执行时能返回完整对象的写入，在进程死亡后若留下半份元数据、半份字节，或从未
持久化的目录项，仍然是错误的。MiniS3 用一套小型文件系统协议让本地崩溃原子性可见：
创建不可变 artifact，flush 文件和目录项，通过原子 rename 发布一个 manifest，再
只依据该 manifest 恢复。在文档规定的 POSIX 假设下，它承诺旧完整状态或新完整状态，
不会出现部分状态。

## 学习目标

完成本章后，你将能够：

- 描述 MiniS3 的桶、对象 artifact 与 manifest 磁盘布局；
- 解释 `临时写 -> 文件 fsync -> rename -> 目录 fsync` 顺序；
- 把 `manifest.json` rename 识别为可见性的线性化点；
- 预测 manifest 发布 hook 前后崩溃的恢复结果；
- 准确说明本地崩溃原子性保证什么、不保证什么。

## 1. 磁盘布局把数据与可见性分开

`src/minis3/storage/disk.py` 中的 `DiskStorage` 拥有以下布局：

```text
buckets/<encoded-bucket>/
  manifest.json
  objects/<sha256-key>/<storage-id>.json
  objects/<sha256-key>/<storage-id>.data
  uploads/...
```

桶名由 `_encoded_name` 做 URL-safe base64 编码。对象 key 由
`_object_directory` 哈希，所以路径形或看似恶意的 key 字符串不会变成文件系统路径。
原始 key 保留在元数据和 manifest 中；这里的 SHA-256 只便于寻址，不是对象完整性
证明。

每个数据版本有一个 `.data` 文件和一个 `.json` 元数据文件。Delete marker 只需
元数据。文件使用唯一内部 `storage_id` 命名，不使用可替换公开 `version_id`。如
第 2 章所示，这让多个公开 null 值能在 commit 期间作为不同不可变 artifact 暂时
共存。

`manifest.json` 包含桶名、版本状态，以及每个 key 所引用的有序 storage ID 列表。
它是权威可达性地图。artifact 单独存在并不会让值可见。

## 2. 持久发布一个文件

可复用原语是 `src/minis3/storage/atomic.py` 中的 `atomic_write`：

```python
with temporary.open("wb") as handle:
    handle.write(payload)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, path)
fsync_directory(path.parent)
```

写同目录临时文件，可避免 final 名称的读者看到部分字节。`handle.flush()` 把 Python
缓冲字节送到操作系统；`os.fsync(handle.fileno())` 请求文件系统持久化文件数据和
必要元数据；同一文件系统内的 `os.replace` 把目录项从旧完整 final 文件原子切换到
新完整文件；最后 `fsync_directory` 持久化该目录项变化。

文件 fsync 与目录 fsync 解决不同问题。文件可持久，不代表为它命名的目录项在掉电后
仍存在；名称可持久，也不代表具名字节已 flush。协议按顺序需要两者。

`durable_mkdir` 向上寻找缺失目录，创建它们，再由外向内 fsync 每个新目录项的父目录。
这堵住了一个细小但关键的洞：即使对象文件完全 flush，如果新建祖先目录从未持久，
文件仍无法恢复。

## 3. 先 Artifact，后 Manifest

`DiskStorage.persist_bucket` 是提交协议。它遍历候选桶引用的每个版本并调用
`_write_artifact`。已有 metadata path 会跳过，因为 artifact 不可变。新数据版本先
原子写 `.data`，再原子写 metadata。

只有每个引用 artifact 都存在后，`persist_bucket` 才执行：

```python
self._inject("before_manifest_publish")
atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
self._inject("after_manifest_publish")
self._clean_bucket(directory, bucket)
```

原子替换 `manifest.json` 是线性化点。在它之前，旧 manifest 只引用旧完整 artifact；
新文件可能已持久，但不可达。在它之后，新 manifest 只引用已经先持久化的 artifact。
清理刻意放在发布之后：若先移除旧 artifact，manifest 切换前就可能破坏旧状态。

崩溃注入器为边界两侧命名。它在新 artifact 持久但 manifest 尚未切换时调用一次，
切换后再调用一次。抛出 `InjectedCrash` 模拟进程骤停，又不会把生产控制流混入机制。

## 4. 服务层候选状态发布

文件系统协议与 `src/minis3/store.py` 中的 `MiniS3.put_object` 成对出现。服务在
进程锁内深拷贝桶，修改副本，调用 `persist_bucket`，最后给 `self._buckets` 赋值。

这个顺序对齐两个可见域：

- 磁盘持久化若在 manifest 发布前失败，运行进程仍持有旧桶；
- manifest 成功发布后，服务安装与之匹配的候选内存状态。

manifest 发布后的注入崩溃会在内存赋值前中断，但模型认为该进程已经死亡。新
`MiniS3` 实例会从已发布 manifest 恢复新状态。因此崩溃测试必须重新打开 store；
继续使用被刻意“撞死”的实例，不能忠实模拟进程死亡。

## 5. 启动恢复

`DiskStorage.load_buckets` 扫描 bucket root。它移除临时桶目录和删除 tombstone，
忽略非目录，并删除没有 manifest 的目录。对已发布桶，它调用 `_load_bucket`，重建
manifest 中具名版本，推进最大 sequence，再调用 `_clean_bucket`。

`_clean_bucket` 计算恢复桶引用的 storage ID 集合，移除临时文件和 stem 不在引用集
中的 artifact，再删除空对象目录。因此 manifest 发布前崩溃只会留下无害新 orphan：
重启信任旧 manifest 并删除 orphan。发布后崩溃则保留新 artifact，因为新 manifest
引用它们；不再引用的旧 artifact 被回收。

恢复不会从残留文件猜测意图。这是一条重要设计原则：让一条小型 committed record
成为权威，其他一切都视为可重建数据或垃圾。

桶创建和删除使用相关目录协议。`DiskStorage.create_bucket` 构建完整初始化的临时桶
目录，fsync 其中的 manifest 与目录，rename 到 final 名称，再 fsync buckets root。
`delete_bucket` 把空桶 rename 成 `.deleted-` tombstone，fsync 后删除，再 fsync
一次。启动可完成任一种临时状态的清理。

## 6. 故障矩阵

关键结果如下：

| 崩溃点 | 已发布 manifest | 重启可见值 | 恢复工作 |
|---|---|---|---|
| 写临时 artifact 时 | 旧 | 旧 | 删除临时文件 |
| artifact 后、manifest rename 前 | 旧 | 旧 | 删除未引用 artifact |
| manifest rename 后、cleanup 前 | 新 | 新 | 删除原先引用的旧 artifact |
| cleanup 后 | 新 | 新 | 很少或没有 |

矩阵不讨论调用者是否收到成功响应，因为 MiniS3 没有网络协议；它描述进程死亡后的
恢复存储状态。

## 7. 动手实验：在边界两侧崩溃

运行：

```bash
uv run python labs/lab_crash_atomicity.py
```

实测输出：

```text
Injected crash at 'before_manifest_publish'
After pre-publish crash: old
Injected crash at 'after_manifest_publish'
After post-publish crash: new
Observed states are complete 'old' or complete 'new', never partial.
```

第一次更新写出新 artifact，在 manifest 切换前崩溃，重开后是 `old`。第二次在切换
后崩溃，重开后是 `new`。`tests/test_storage.py` 用 orphan 清理、临时文件清理、
目录 fsync 链，以及同一发布点两侧的 multipart complete 断言强化了 lab。

实验使用直接文件操作和临时本地目录，不需要 socket 或外部服务。

## 8. 与 Amazon S3 对照

[映射矩阵](../mapping.md)把 manifest rename 标为 **Intentional
simplification**。它教授原子元数据可见性和完整本地 fsync 链。Amazon S3 并不是用
一个 POSIX 目录和一份 JSON manifest 实现其全球服务；其持久性与可用性来自分布式
存储、复制或编码、故障检测、修复以及多节点元数据协议，MiniS3 都不模拟。

MiniS3 的承诺依赖本地文件系统遵守预期的同文件系统原子 rename 与 fsync 语义。
它不覆盖磁盘故障、忽略 flush 的控制器缓存、bit rot、文件系统 bug、多进程 writer、
复制持久性、quorum 行为、在线 scrub 或损坏 manifest 修复；合法已发布 manifest
会被信任。这些限制在[与 Amazon S3 的差异](../DIFFERENCES.md)的持久性、恢复和
并发条目中明确列出。

因此正确表述是“在所述 POSIX 假设下提供旧或新可见性的本地崩溃一致协议”，不是
“11 个 9 的持久性”，也不是“S3 的内部架构”。

## 练习

### 理解题

1. 为什么新 artifact 必须在 manifest 被替换前持久化？
2. 为什么 `os.replace` 后只对临时文件执行过的 `fsync` 还不够？
3. 为什么恢复信任 manifest，而不选择文件名最新的 artifact？

??? note "参考答案"

    1. 发布后每个 manifest 引用都必须指向完整持久 artifact。先发布可能让新状态在
       崩溃后指向缺失或部分字节。
    2. Rename 改变目录项。文件字节可能持久，而新名称没有持久；fsync 父目录才能
       持久命名变化。
    3. artifact 存在并不编码事务意图。manifest 是唯一 commit record；按文件名选择
       可能暴露一个提交前已崩溃的写入。

### 动手题

4. 不修改 `src/`，把 lab 模式复制到内联脚本，在 `before_manifest_publish`
   注入崩溃。重开后断言失败更新没有留下未引用 `e*.data` 或 `e*.json`。

   **验收方式：**GET 返回旧 body；artifact 列表只包含 manifest 引用的旧 storage
   ID；`uv run pytest -q` 保持全绿。

??? note "参考答案"

    重开后用 `json.loads` 检查唯一 bucket manifest，收集其引用 storage ID，与
    artifact 文件 stem 比较：

    ```python
    manifest_path = next((Path(root) / "buckets").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    referenced = {
        storage_id
        for ids in manifest["records"].values()
        for storage_id in ids
    }
    artifacts = {
        path.stem
        for path in (Path(root) / "buckets").rglob("e*.*")
    }
    assert artifacts == referenced
    ```

    需导入 `json` 和 `Path`。只在实验中使用，不要让生产代码依赖 manifest 内部格式。

5. 提出但不要应用一个针对 `after_object_directory_create` 的故障注入测试 diff。

   **验收方式：**提案在 `InjectedCrash` 后重开 store，检查旧对象视图仍合法，并
   解释该 hook 测的是目录 fsync 链，而不只是 manifest 原子性。

??? note "参考答案"

    测试应构造 `CrashOnce("after_object_directory_create")`，为尚无哈希目录的 key
    尝试 PUT，预期 `InjectedCrash`，再重新打开。新 key 应不存在，已有 key 仍可读。
    该崩溃发生在新对象目录的父目录 fsync 前，也在 manifest 发布前，因此它单独探测
    持久目录创建这一前置条件。

## 小结

MiniS3 把持久 artifact 与可见可达性分开。原子写会 flush 临时文件、rename，再 flush
父目录；新建目录链也会持久化。`persist_bucket` 先写不可变 artifact，最后发布一份
权威 manifest。恢复信任该 manifest 并清理其他内容，于提交点两侧产生旧或新完整
状态。第 6 章将为 multipart upload 复用同一发布边界：私有暂存 part 只在 complete
时成为一个可见对象。
