# Stage 14 · Deterministic lifecycle expiration / 确定性生命周期过期

<!-- journey: chapter=8 tests_added=4 -->

## English

### Goal

Separate pure expiration decisions from an explicit mutation tick driven by an injected clock.

### Deliverable files

- `src/minis3/__init__.py`
- `src/minis3/lifecycle.py`
- `src/minis3/store.py`
- `tests/test_lifecycle.py`

### The problem at this point

Versions now carry creation times, but nothing expires them. Hiding time reads inside policy or background threads would make boundary behavior nondeterministic and combine “what should happen” with “apply it now.”

### Failure preview

The pure-boundary contract evaluates the same history at time `9.999` and `10.0`. No action is allowed before the threshold; the action appears exactly at it. A hidden wall clock or strict `>` comparison makes this boundary flaky or one tick late.

### Basic concepts

Policy evaluation is a pure calculation from immutable history, rules, and explicit `now`. It emits `LifecycleAction` decisions. `lifecycle_tick` is the separate mutation boundary that applies those decisions under the service lock and persists only when state changes.

Expiring a current data version creates a delete marker so older history stays hidden. Expiring a noncurrent version physically removes that addressed historical item.

### Why this mechanism is necessary

Pure evaluation can be reasoned about and repeated without side effects. An injected clock makes tests and replay deterministic. An explicit tick also makes it clear when durability and locking obligations begin.

### Runtime mental model

The caller invokes `lifecycle_tick` with rules. The service captures injected time, deep-copies the Bucket, calls `evaluate_expiration`, applies each action through Bucket deletion semantics, persists the candidate if actions exist, swaps it, and returns the action list.

### File-by-file walkthrough

<!-- journey-file: src/minis3/lifecycle.py -->
#### `src/minis3/lifecycle.py`

##### What it is and why it appears

This pure policy module defines expiration rules, action values, and decision evaluation.

##### Runtime role

It reads histories and returns what should change; it never calls storage or mutates Bucket records.

##### Key code

```python
return threshold is not None and now - created_at >= threshold
```

##### Statement understanding

`>=` makes the policy boundary inclusive and deterministic. `None` means that category has no expiration rule, not age zero.

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

The service adds the explicit tick that converts pure actions into durable state transitions.

##### Runtime role

It supplies one time value and stable snapshot under the lock, then reuses Bucket deletion and candidate publication.

##### Key code

```python
self._storage.persist_bucket(candidate)
```

##### Statement understanding

Policy output alone changes nothing. Persisting the candidate is what makes an applied expiration survive restart; no-action ticks avoid needless publication.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

Rules and action types join the public learning API.

##### Runtime role

Callers can construct policy and inspect returned decisions without depending on lifecycle internals.

##### Statement understanding

The package exports declarative values, while actual mutation remains a `MiniS3` operation.

<!-- journey-file: tests/test_lifecycle.py -->
#### `tests/test_lifecycle.py`

##### What it is and why it appears

Four contracts cover pure filtering/boundaries, current versus noncurrent transitions, injected time/restart, and invalid rules.

##### Runtime role

`ManualClock` lets tests advance time deliberately and prove persisted timestamps rather than waiting on wall time.

##### Key code

```python
assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
```

##### Statement understanding

This is the just-before boundary. Paired with the `10.0` assertion, it proves inclusion precisely rather than merely testing an obviously old object.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/14-lifecycle-tick/tests.txt)`. The cases prove pure policy, explicit mutation, time injection, restart persistence, and rule validation.

### Durable takeaways

Decide purely, mutate explicitly, inject time, and persist only applied actions. Current expiration creates a marker; noncurrent expiration removes one historical version.

### Explain it in your own words

MiniS3 separates lifecycle policy from execution. A pure function decides actions from history, rules, and an explicit clock; a locked tick applies those actions through existing version semantics and publishes the resulting Bucket so time-based behavior remains deterministic and recoverable.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/08-lifecycle.md)

## 中文

### 目标

把纯过期决策与由注入时钟驱动的显式变更 tick 分开。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/lifecycle.py`
- `src/minis3/store.py`
- `tests/test_lifecycle.py`

### 当前遇到的问题

Version 已有创建时间，但没有任何机制让它们过期。把时间读取藏进策略或后台线程，会让边界行为不确定，并把“应该发生什么”和“现在执行”混在一起。

### 先看会坏在哪里

纯边界契约在时间 `9.999` 与 `10.0` 对同一历史求值。阈值前不能有 action，到达时必须出现。隐藏 wall clock 或使用严格 `>` 会让边界 flaky 或晚一个 tick。

### 基本概念

策略求值是不可变历史、规则和显式 `now` 的纯计算，输出 `LifecycleAction` 决策。`lifecycle_tick` 是独立变更边界，在服务锁内应用决策，并只在状态变化时持久化。

当前数据版本过期会创建删除标记，使旧历史继续隐藏；非当前版本过期则物理移除被寻址的历史项。

### 为什么需要这个机制

纯求值可无副作用重复推理；注入 clock 让测试和重放确定；显式 tick 还明确了锁与持久化义务从哪里开始。

### 运行时心智模型

调用方用规则调用 `lifecycle_tick`。服务取得注入时间、深拷贝 Bucket、调用 `evaluate_expiration`、通过 Bucket 删除语义应用每个 action；有 action 时持久化并替换候选，最后返回 action 列表。

### 逐文件走读

<!-- journey-file: src/minis3/lifecycle.py -->
#### `src/minis3/lifecycle.py`

##### 是什么，为什么现在需要

这个纯策略模块定义过期规则、action 值和决策求值。

##### 在运行时做什么

它读取历史并返回应该改变什么，从不调用存储或修改 Bucket records。

##### 关键代码

```python
return threshold is not None and now - created_at >= threshold
```

##### 关键语句理解

`>=` 让策略边界包含阈值且确定；`None` 表示该类别没有过期规则，不是年龄零。

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

服务增加把纯 action 转成持久状态迁移的显式 tick。

##### 在运行时做什么

它在锁内提供一个时间值与稳定快照，再复用 Bucket 删除和候选发布。

##### 关键代码

```python
self._storage.persist_bucket(candidate)
```

##### 关键语句理解

策略输出本身不改变任何状态。持久化候选才让过期跨重启保存；无 action tick 不必发布。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

规则与 action 类型加入公开学习 API。

##### 在运行时做什么

调用方可构造策略、检查返回决策，而不依赖生命周期内部实现。

##### 关键语句理解

包导出声明式值，实际变更仍是 `MiniS3` 操作。

<!-- journey-file: tests/test_lifecycle.py -->
#### `tests/test_lifecycle.py`

##### 是什么，为什么现在需要

四条契约覆盖纯过滤/边界、当前与非当前迁移、注入时间/重启和非法规则。

##### 在运行时做什么

`ManualClock` 让测试主动推进时间，证明持久时间戳，而不是等待 wall time。

##### 关键代码

```python
assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
```

##### 关键语句理解

这是刚到阈值前的边界；与 `10.0` 断言成对后，精确证明 inclusive，而不是只测明显过期对象。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/14-lifecycle-tick/tests.txt)`。用例证明纯策略、显式变更、时间注入、重启持久化与规则校验。

### 需要真正记住的内容

纯计算决定、显式 tick 变更、时间可注入、只持久化已应用 action；当前过期建 Marker，非当前过期删除一个历史版本。

### 用自己的话讲清楚

MiniS3 把生命周期策略和执行分开。纯函数根据历史、规则与显式时钟决定 action；带锁 tick 通过已有版本语义应用并发布结果，使时间行为确定且可恢复。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/08-lifecycle.md)
