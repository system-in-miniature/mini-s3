# Stage 13 · Conditional requests and CAS / 条件请求与 CAS

<!-- journey: chapter=7 tests_added=4 -->

## English

### Goal

Use ETags as cache validators and serialized compare-and-swap preconditions for reads and mutations.

### Deliverable files / 交付文件

- `src/minis3/__init__.py`
- `src/minis3/conditional.py`
- `src/minis3/errors.py`
- `src/minis3/store.py`
- `tests/test_conditional.py`

### The problem at this point

ETags exist but callers cannot make an operation conditional on the value they observed. A stale writer can overwrite a newer value, and a cache cannot ask whether its copy is still current without downloading the body again.

### Failure preview

The concurrency contract starts two writers with the same initial ETag. Exactly one may pass `If-Match`; the second must see the changed current ETag and fail. If the check occurs outside the mutation lock, both can validate stale state and both appear to win.

### Basic concepts

`If-None-Match` on GET is a cache validator: a match means the representation is not modified (304-shaped). `If-Match` is a precondition: mismatch means the requested operation cannot be applied to the addressed current state (412-shaped).

Compare-and-swap means “change only if the current identity still equals what I observed.” Correctness depends on checking and mutating within one serialized critical section, not just on comparing strings.

### Why this mechanism is necessary

Without preconditions, read-modify-write clients lose updates. Without distinct 304/412 failures, callers cannot tell a successful cache validation from a rejected mutation. Central match helpers keep wildcard and comma-list behavior consistent.

### Runtime mental model

The service acquires its lock, resolves the current or addressed ETag, applies `require_if_match`/`require_if_none_match`, and only then reads or mutates. A successful PUT changes the ETag before the next waiting writer performs its check.

### File-by-file walkthrough

<!-- journey-file: src/minis3/conditional.py -->
#### `src/minis3/conditional.py`

##### What it is and why it appears

This pure policy module parses ETag conditions and raises the correct semantic failure.

##### Runtime role

Store supplies the current ETag; the helpers decide match, precondition failure, or not-modified without owning locks or state.

##### Key code

```python
if condition is not None and not etag_matches(condition, current_etag):
    raise PreconditionFailed(condition)
```

##### Statement understanding

Absent condition means no guard. A present nonmatch must stop the operation before mutation; returning `False` for the caller to ignore would weaken the contract.

<!-- journey-file: src/minis3/errors.py -->
#### `src/minis3/errors.py`

##### What it is and why it appears

The failure vocabulary gains distinct precondition-failed and not-modified outcomes.

##### Runtime role

Protocol adapters can later map them to 412 and 304 without embedding HTTP in the domain service.

##### Key code

```python
class NotModified(MiniS3Error):
```

##### Statement understanding

Not-modified is control-flow evidence for a validator, not the same error as a mutation rejected against stale state.

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### What it is and why it appears

Public GET, PUT, and DELETE accept conditional parameters and evaluate them inside existing locks.

##### Runtime role

It owns atomicity between current-ETag lookup, precondition decision, and any subsequent Bucket mutation/publication.

##### Key code

```python
require_if_match(self._current_etag(candidate, key), if_match)
```

##### Statement understanding

The check reads from the candidate snapshot while the service lock is held. No other writer can change the current visible ETag between this line and mutation.

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### What it is and why it appears

Conditional failures become part of the supported API.

##### Runtime role

Callers catch semantic outcomes from the package root; match helpers remain internal policy.

##### Statement understanding

Exposing outcome types but not parsing internals keeps the public surface small.

<!-- journey-file: tests/test_conditional.py -->
#### `tests/test_conditional.py`

##### What it is and why it appears

Four contracts cover GET validators, mutation guards, wildcard behavior, and the two-writer CAS race.

##### Runtime role

The threaded test proves serialization behavior that a sequential helper unit test cannot establish.

##### Key code

```python
assert sorted(outcomes) == ["412", "stored"]
```

##### Statement understanding

One `stored` and one `412` is the externally visible CAS guarantee. Two stored outcomes would prove the check and mutation were not atomic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`. The cases prove matching forms, failure meanings, mutation guards, and one-winner concurrency.

### Durable takeaways

ETag comparison becomes safe concurrency control only when check and mutation share the same lock. 304-style validation and 412-style rejection are different outcomes.

### Explain it in your own words

Conditional requests let a caller act on the exact value it observed. MiniS3 evaluates the ETag guard inside the service's mutation lock, so one writer can commit and every stale competitor then fails against the new current ETag instead of overwriting it.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/07-conditional.md)

## 中文

### 目标

把 ETag 用作缓存校验器，以及读取和变更的串行 compare-and-swap 前置条件。

### 交付文件

- `src/minis3/__init__.py`
- `src/minis3/conditional.py`
- `src/minis3/errors.py`
- `src/minis3/store.py`
- `tests/test_conditional.py`

### 当前遇到的问题

系统已有 ETag，但调用方还不能要求“只在我看到的值仍是当前值时操作”。旧写入者可能覆盖新值，缓存也无法在不下载 Body 的情况下询问副本是否仍然有效。

### 先看会坏在哪里

并发契约让两个写入者携带相同初始 ETag。只能有一个通过 `If-Match`；第二个必须看到变化后的当前 ETag 并失败。如果检查在变更锁外，两者都可能校验旧状态并同时获胜。

### 基本概念

GET 的 `If-None-Match` 是缓存校验：匹配表示 representation 未修改（304 语义）。`If-Match` 是前置条件：不匹配表示请求不能作用于当前状态（412 语义）。

Compare-and-swap 表示“只有当前身份仍等于我观察到的身份才修改”。正确性依赖在同一串行临界区内完成检查和变更，而不只是比较字符串。

### 为什么需要这个机制

缺少前置条件时，read-modify-write 客户端会丢失更新。缺少不同的 304/412 失败，调用方无法区分缓存命中和变更被拒绝。集中匹配 helper 还能统一 wildcard 与逗号列表规则。

### 运行时心智模型

服务获得锁，解析当前或指定版本 ETag，执行 `require_if_match`/`require_if_none_match`，之后才读取或变更。成功 PUT 会在下一名等待写入者检查前改变 ETag。

### 逐文件走读

<!-- journey-file: src/minis3/conditional.py -->
#### `src/minis3/conditional.py`

##### 是什么，为什么现在需要

这个纯策略模块解析 ETag 条件并抛出正确语义失败。

##### 在运行时做什么

Store 提供当前 ETag；helper 决定匹配、前置条件失败或未修改，不拥有锁和状态。

##### 关键代码

```python
if condition is not None and not etag_matches(condition, current_etag):
    raise PreconditionFailed(condition)
```

##### 关键语句理解

条件缺失表示不加 guard；条件存在但不匹配必须在变更前停止。只返回可能被调用方忽略的 `False` 会削弱契约。

<!-- journey-file: src/minis3/errors.py -->
#### `src/minis3/errors.py`

##### 是什么，为什么现在需要

失败词汇增加前置条件失败与未修改两个不同结果。

##### 在运行时做什么

协议适配器以后可分别映射 412 与 304，而领域服务无需嵌入 HTTP。

##### 关键代码

```python
class NotModified(MiniS3Error):
```

##### 关键语句理解

Not-modified 是校验器的控制流证据，不能和针对旧状态的变更拒绝混成同一错误。

<!-- journey-file: src/minis3/store.py -->
#### `src/minis3/store.py`

##### 是什么，为什么现在需要

公开 GET、PUT、DELETE 接受条件参数，并在已有锁内计算。

##### 在运行时做什么

它拥有当前 ETag 查找、前置条件决定与后续 Bucket 变更/发布之间的原子性。

##### 关键代码

```python
require_if_match(self._current_etag(candidate, key), if_match)
```

##### 关键语句理解

检查在服务锁内读取候选快照；从这行到变更之间，不会有其他写入者改变当前可见 ETag。

<!-- journey-file: src/minis3/__init__.py -->
#### `src/minis3/__init__.py`

##### 是什么，为什么现在需要

条件请求失败成为受支持 API。

##### 在运行时做什么

调用方从包根捕获语义结果，匹配 helper 继续作为内部策略。

##### 关键语句理解

公开结果类型但不公开解析内部细节，可以保持 API 较小。

<!-- journey-file: tests/test_conditional.py -->
#### `tests/test_conditional.py`

##### 是什么，为什么现在需要

四条契约覆盖 GET 校验、变更 guard、wildcard 和双写者 CAS 竞争。

##### 在运行时做什么

线程测试证明顺序 helper 单测无法证明的串行化行为。

##### 关键代码

```python
assert sorted(outcomes) == ["412", "stored"]
```

##### 关键语句理解

一个 `stored` 与一个 `412` 是外部可见 CAS 保证；两个 stored 会证明检查与变更并不原子。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/13-conditional-cas/tests.txt)`。用例证明匹配形式、失败含义、变更 guard 和单赢家并发。

### 需要真正记住的内容

ETag 比较只有在检查与变更共享同一把锁时才成为安全并发控制；304 校验与 412 拒绝是不同结果。

### 用自己的话讲清楚

条件请求让调用方只对自己观察过的精确值采取行动。MiniS3 在服务变更锁内计算 ETag guard，所以一名写入者提交后，所有旧竞争者会面对新的当前 ETag 失败，而不是覆盖它。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-s3/blob/main/docs/zh/tutorial/07-conditional.md)
