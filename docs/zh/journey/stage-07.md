# Stage 07 · Manifest 发布崩溃矩阵

### 目标

在 manifest rename 前后注入崩溃，钉死其线性化点。

### 交付文件

- `tests/test_storage.py`

### 机制走读

#### 所有权与数据流

本阶段只修改测试，不修改生产代码；故障注入包围 Manifest 替换，以证明单一线性化点两侧的旧/新可见性分界。

#### 失败与排查

每次注入崩溃后重新打开存储，只观察已发布状态；若看到部分新状态，说明发布顺序或恢复信任边界错误。

### 逐文件 Diff 走读

按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。

#### `tests/test_storage.py`

本阶段行为的可执行证明。

调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

**变化锚点:** `test_crash_before_manifest_publish_leaves_old_state`, `test_crash_before_manifest_publication_matrix_leaves_old_state`, `test_crash_after_manifest_publish_exposes_complete_new_state`

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

### 验证证据

`uv run pytest -q $(cat journey/stages/07-publication-crash-matrix/tests.txt)`

本阶段新增 5 个可执行用例，入口为 `test_crash_before_manifest_publish_leaves_old_state`、`test_crash_before_manifest_publication_matrix_leaves_old_state`、`test_crash_after_manifest_publish_exposes_complete_new_state`。它们在机制走读之后运行，并与此前 Stage 的用例一起守住累计行为。

### 概念检查

本阶段完成后，哪条不变量必须保持成立？

??? note "答案"
    rename 前恢复到旧状态；rename 后看到完整新状态。

### 代码阅读检查

从 `tests/test_storage.py` 的 `test_crash_before_manifest_publish_leaves_old_state` 开始：进入这个边界的状态或值是什么，结果又交给哪个所有者？

??? note "答案"
    调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。

### 面试表达

rename 前恢复到旧状态；rename 后看到完整新状态。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/05-crash-atomicity.md)

[在 GitHub 查看阶段差异](https://github.com/system-in-miniature/mini-s3/compare/stage-06...stage-07)

完成后可运行 `git checkout stage-07` 对照你的结果。

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/07-publication-crash-matrix/stage.patch)
