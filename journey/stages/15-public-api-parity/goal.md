# Stage 15 · Public API and parity closeout / 公开 API 与守链收官

<!-- journey: chapter=9 tests_added=0 -->

## English

### Goal

Expose the complete teaching API and prove the stage-built source and Journey tests match main byte for byte.

### Deliverable files

- `src/minis3/__init__.py`

### The problem at this point

All mechanisms exist, but accumulated imports can still expose accidental names or omit intended ones. Passing behavioral tests also does not by itself prove the Journey reconstructs the exact maintained source and test corpus.

### Failure preview

The parity command rebuilds every patch into a fresh tree and compares bytes with main. One missing export line or stale stage test makes the check fail even if a narrow pytest selection remains green. This catches drift between the learning path and finished repository.

### Basic concepts

A public API is an intentional compatibility boundary, not every name currently importable from a module. `__all__` records that choice. Source parity and behavioral evidence are complementary: tests prove selected semantics; byte comparison proves the reconstruction artifact is the maintained artifact.

### Why this mechanism is necessary

A course can slowly become a detached toy while its examples still pass. Closing with exact exports and byte parity makes source alignment an enforceable property rather than a README claim.

### Runtime mental model

User imports resolve through `src/minis3/__init__.py`. Separately, `build_journey.py --check` starts from the empty Journey root, applies all 15 canonical patches, gathers Journey-owned tests, and compares reconstructed bytes to the current main tree without moving refs.

### Mechanism blocks

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

The package root receives its final explicit export list for values, services, policies, results, and public failures.

##### Runtime role

It is the stable learner-facing import boundary. Internal storage helpers and implementation-only functions remain absent.

##### Key code

```python
__all__ = [
```

##### Statement understanding

The list converts an implicit collection of imports into a deliberate contract. Adding an internal helper elsewhere no longer makes it public accidentally.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)` for the cumulative suite, then `python journey/tools/build_journey.py --check` for byte-for-byte source and Journey-test parity. Stage 15 adds no new behavior case because its deliverable is the public surface and reconstruction proof.

### Durable takeaways

An import surface, passing tests, and byte parity prove different things. Completion requires all three to agree with the intended course boundary.

### Explain it in your own words

The final Stage makes the learning journey auditable. `__all__` states which concepts are supported publicly, cumulative tests prove their behavior, and the parity rebuild proves the sequence of stages reconstructs the same source and tests maintained on main.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/09-methodology.md)

## 中文

### 目标

公开完整教学 API，并证明按 Stage 构建的源码与 Journey 测试逐字节等于 main。

### 交付文件

- `src/minis3/__init__.py`

### 当前遇到的问题

所有机制都已存在，但累积 import 仍可能意外公开内部名称，或漏掉预期名称。行为测试通过也不能单独证明 Journey 重建的是当前维护的精确源码与测试集合。

### 先看会坏在哪里

Parity 命令在全新树中重放每个 patch，再与 main 比较字节。即使窄范围 pytest 仍绿，只要漏一条 export 或 Stage 测试过期，检查就会失败。这直接捕获学习路径与完成仓库之间的漂移。

### 基本概念

公开 API 是有意选择的兼容边界，不是模块里当前能 import 的全部名称。`__all__` 记录这个选择。源码 parity 与行为证据互补：测试证明选定语义，字节比较证明重建 Artifact 就是维护中的 Artifact。

### 为什么需要这个机制

课程可能逐渐变成脱离源码的 toy，同时自己的示例仍然通过。用精确 export 与字节 parity 收官，能把源码对齐变成可执行属性，而不是 README 声明。

### 运行时心智模型

用户 import 通过 `src/minis3/__init__.py` 解析。另一边，`build_journey.py --check` 从空 Journey 根开始应用 15 个 canonical patch，收集 Journey 自有测试，再把重建字节与当前 main 比较，不移动 refs。

### 机制板块

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

包根得到最终显式导出列表，覆盖值、服务、策略、结果与公开失败。

##### 在运行时做什么

它是稳定的学习者导入边界；内部存储 helper 和实现函数继续不公开。

##### 关键代码

```python
__all__ = [
```

##### 关键语句理解

这份列表把隐式 imports 集合变成有意契约；以后在内部增加 helper，也不会意外变成公开 API。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/15-public-api-parity/tests.txt)` 执行累计套件，再运行 `python journey/tools/build_journey.py --check` 做源码与 Journey 测试逐字节 parity。Stage 15 不新增行为用例，因为交付物就是公开面与重建证明。

### 需要真正记住的内容

Import 面、测试通过和字节 parity 各自证明不同内容；完成要求三者都与预期课程边界一致。

### 用自己的话讲清楚

最终 Stage 让学习旅程可审计：`__all__` 声明哪些概念受公开支持，累计测试证明行为，parity 重建证明整段 Stage 序列得到的就是 main 维护的源码与测试。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/09-methodology.md)
