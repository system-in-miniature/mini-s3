# Stage 07 · Manifest 发布崩溃矩阵

### 目标

在 Manifest rename 前后立即崩溃，证明它是唯一可见性边界。

??? note "交付文件"
    - `tests/test_storage.py`

### 当前遇到的问题

Stage 03 描述了最后发布的存储，正常重启也通过了，但这还不能证明崩溃只会暴露完整旧状态或完整新状态。必须在每个命名崩溃边界实际观察。

### 测试契约

#### 先看会坏在哪里

一条测试在新 Artifact 已持久化后注入 `before_manifest_publish`。重开后必须仍返回旧对象并删除未引用的新 Artifact。如果 Artifact 只要存在就算可见，新值会在 Manifest 从未提交时泄漏。

??? note "文件差异：tests/test_storage.py"
    ```diff
    diff --git a/tests/test_storage.py b/tests/test_storage.py
    index c96a7a6..5faad97 100644
    --- a/tests/test_storage.py
    +++ b/tests/test_storage.py
    @@ -30,3 +30,69 @@ def test_restart_restores_versions_bodies_and_counter(tmp_path: Path) -> None:

         assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
         assert second.version_id != first.version_id
    +
    +
    +def test_crash_before_manifest_publish_leaves_old_state(tmp_path: Path) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    crashing = MiniS3(
    +        tmp_path,
    +        counter=SequenceCounter(10),
    +        crash_injector=CrashOnce("before_manifest_publish"),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.put_object("b", "new", b"value")
    +
    +    reopened = MiniS3(tmp_path)
    +    with pytest.raises(NoSuchKey):
    +        reopened.get_object("b", "new")
    +    assert not list(tmp_path.rglob("*.tmp-*"))
    +    assert not list(tmp_path.rglob("e00000010.*"))
    +
    +
    +@pytest.mark.parametrize(
    +    "crash_point",
    +    [
    +        "after_object_directory_create",
    +        "after_object_directory_parent_fsync",
    +        "before_manifest_publish",
    +    ],
    +)
    +def test_crash_before_manifest_publication_matrix_leaves_old_state(
    +    tmp_path: Path,
    +    crash_point: str,
    +) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    crashing = MiniS3(
    +        tmp_path,
    +        counter=SequenceCounter(10),
    +        crash_injector=CrashOnce(crash_point),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.put_object("b", "new", b"value")
    +
    +    reopened = MiniS3(tmp_path)
    +    with pytest.raises(NoSuchKey):
    +        reopened.get_object("b", "new")
    +    assert not list(tmp_path.rglob("*.tmp-*"))
    +    assert not list(tmp_path.rglob("e00000010.*"))
    +
    +
    +def test_crash_after_manifest_publish_exposes_complete_new_state(
    +    tmp_path: Path,
    +) -> None:
    +    MiniS3(tmp_path).create_bucket("b")
    +    crashing = MiniS3(
    +        tmp_path,
    +        counter=SequenceCounter(10),
    +        crash_injector=CrashOnce("after_manifest_publish"),
    +    )
    +
    +    with pytest.raises(InjectedCrash):
    +        crashing.put_object("b", "new", b"value")
    +
    +    reopened = MiniS3(tmp_path)
    +    visible = reopened.get_object("b", "new")
    +    assert visible.body == b"value"
    +    assert visible.etag == '"2063c1608d6e0baf80249c42e2be5804"'
    ```

**测试锁定什么**

存储集成套件加入围绕 Artifact 与 Manifest 发布的参数化崩溃矩阵。

**如何构造反例**

它只在重开后观察系统，丢弃可能误导人的进程内内存，并实际运行恢复清理。

**关键测试语句**

```python
crash_injector=CrashOnce("before_manifest_publish"),
```

**失败意味着什么**

命名 hook 固定精确中断边界；全新实例上的断言因而能区分“Artifact 已持久化”和“状态已发布”。

### 基本概念

线性化点是并发或恢复观察者认为操作已经生效的瞬间。崩溃矩阵探测它两侧：点之前旧状态获胜，点之后完整新状态获胜，不允许半状态。

### 为什么需要这个机制

文档和 happy path 无法证明崩溃原子性。故意中断把发布顺序变成可执行证据，也防止未来重构误把可见性移动到 Artifact 创建时。

### 运行时心智模型

测试准备旧状态、安装 `CrashOnce`、尝试变更、捕获 `InjectedCrash`，再创建全新服务。随后检查可见数据与磁盘残留。本 Stage 不改生产代码，新增的是对现有边界的可信证据。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`。五个新增用例覆盖多个发布前点、发布后侧与清理。

### 需要真正记住的内容

Artifact 持久化不等于可见。Manifest rename 是提交点：此前恢复选择旧状态，此后恢复选择完整新状态。

### 用自己的话讲清楚

崩溃矩阵通过在线性化点两侧中断并从磁盘重开来证明原子性。只有 Manifest 能让不可变 Artifact 可见，所以发布前未引用文件只是残留，rename 后已发布 Manifest 则提交完整新值。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-06...stage-07)

完成后可运行 `git checkout stage-07` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/07-publication-crash-matrix/stage.patch)
