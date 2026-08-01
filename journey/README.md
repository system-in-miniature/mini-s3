# MiniS3 Journey / MiniS3 重建旅程

Journey Mode turns the finished MiniS3 system into 15 cumulative, testable
rebuild stages. Each generated browser page is a complete lesson: understand
the mechanism, follow its data flow, read every changed file separately, and
then use `tests.txt` plus the checks as the gate.

Journey Mode 把 MiniS3 成品系统拆成 15 个可累积、可测试的重建阶段。每个生成
网页本身就是完整课程：先理解机制与数据流，再逐文件阅读变化，最后用
`tests.txt`、理解题与面试表达完成闭环。

| Stage | Topic / 主题 | New tests / 新增测试 | Book / 教材 |
|---:|---|---:|---:|
| 01 | Scaffold and object values / 脚手架与对象值 | 3 | 1 |
| 02 | Bucket state and deterministic IDs / Bucket 状态与确定性 ID | 1 | 3 |
| 03 | Durable storage boundary / 持久化存储边界 | 1 | 5 |
| 04 | Object service facade / 对象服务门面 | 15 | 2 |
| 05 | Version history projection / 版本历史投影 | 3 | 3 |
| 06 | Listing and directory illusion / Listing 与目录幻觉 | 5 | 4 |
| 07 | Manifest publication crash matrix / Manifest 发布崩溃矩阵 | 5 | 5 |
| 08 | Directory fsync and cleanup / 目录 fsync 与启动清理 | 3 | 5 |
| 09 | Multipart domain and validation / Multipart 领域与校验 | 1 | 6 |
| 10 | Durable multipart staging / Multipart 持久暂存 | 1 | 6 |
| 11 | Atomic multipart completion / Multipart 原子完成 | 4 | 6 |
| 12 | Multipart crash recovery / Multipart 崩溃恢复 | 2 | 6 |
| 13 | Conditional requests and CAS / 条件请求与 CAS | 4 | 7 |
| 14 | Deterministic lifecycle expiration / 确定性生命周期过期 | 4 | 8 |
| 15 | Public API and parity closeout / 公开 API 与守链收官 | 0 | 9 |

## Learn in VSCode / 在 VSCode 中学习

Show one stage as editor-native, uncommitted changes in a dedicated learning
repository (default: `../MiniS3-journey-workspace`; the main checkout is never
modified):

```bash
python journey/tools/build_journey.py study 3
code ../MiniS3-journey-workspace
```

Start from the same stage-02 baseline but implement stage 03 yourself, then run
its cumulative test subset and compare your current tree with the patch-built
stage-03 reference:

```bash
python journey/tools/build_journey.py attempt 3
python journey/tools/build_journey.py check 3
```

`study` and `attempt` ask before replacing existing work. Pass `--yes` to skip
that prompt, or `--workspace PATH` to use another dedicated repository.

`study 3` 会在专用学习仓库中提交 stage-02 累积状态作为基线，再把 stage-03
补丁以**未提交变更**应用；VSCode gutter 和 Source Control 因而只显示当前
stage。`attempt 3` 回到同一干净基线供你自己实现，`check 3` 运行累计测试并
输出当前树相对 patch 累积参考树的 `git diff --stat`。主工作区始终不会被修改。
重复执行 `study`/`attempt` 前会明确确认覆盖；可用 `--yes` 跳过，或用
`--workspace PATH` 指定其他专用仓库。

Verify without changing refs:

```bash
python journey/tools/build_journey.py --check
```

After maintainer acceptance, omit `--check` to rebuild the orphan `journey`
branch and `stage-NN` tags.


> `journey attempt` remains an experimental self-implementation path. It is not required for the complete browser or tutor-guided course, and test-first implementation is not the default teaching order.
