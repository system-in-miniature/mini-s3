# MiniS3 Journey

从空目录开始，依次完成任务卡；先动手，卡住时再展开补丁。

## 在 VSCode 中学习

使用专用学习仓库，让 VSCode gutter 与 Source Control 只显示当前 stage；
主工作区始终不会被修改。

```bash
python journey/tools/build_journey.py study 3
code ../MiniS3-journey-workspace
```

如果要自己实现，先准备上一 stage 的干净基线，再检查当前成果：

```bash
python journey/tools/build_journey.py attempt 3
python journey/tools/build_journey.py check 3
```

`check` 会运行该 stage 的累计 `tests.txt` 子集，并输出当前树相对补丁直接
累积出的参考树的 `git diff --stat`。`study` 和 `attempt` 覆盖已有学习内容前
会明确确认；用 `--yes` 跳过提示，或用 `--workspace PATH` 选择其他专用仓库。

| Stage | 主题 | 新增测试 | 教材章节 |
|---:|---|---:|---:|
| [01](stage-01.md) | 脚手架与对象值 | 3 | [1](../tutorial/01-getting-started.md) |
| [02](stage-02.md) | Bucket 状态与确定性 ID | 0 | [3](../tutorial/03-versioning.md) |
| [03](stage-03.md) | 持久化存储边界 | 0 | [5](../tutorial/05-crash-atomicity.md) |
| [04](stage-04.md) | 对象服务门面 | 15 | [2](../tutorial/02-objects-etag.md) |
| [05](stage-05.md) | 版本历史投影 | 3 | [3](../tutorial/03-versioning.md) |
| [06](stage-06.md) | Listing 与目录幻觉 | 5 | [4](../tutorial/04-listing.md) |
| [07](stage-07.md) | Manifest 发布崩溃矩阵 | 5 | [5](../tutorial/05-crash-atomicity.md) |
| [08](stage-08.md) | 目录 fsync 与启动清理 | 3 | [5](../tutorial/05-crash-atomicity.md) |
| [09](stage-09.md) | Multipart 领域与校验 | 0 | [6](../tutorial/06-multipart.md) |
| [10](stage-10.md) | Multipart 持久暂存 | 1 | [6](../tutorial/06-multipart.md) |
| [11](stage-11.md) | Multipart 原子完成 | 4 | [6](../tutorial/06-multipart.md) |
| [12](stage-12.md) | Multipart 崩溃恢复 | 2 | [6](../tutorial/06-multipart.md) |
| [13](stage-13.md) | 条件请求与 CAS | 4 | [7](../tutorial/07-conditional.md) |
| [14](stage-14.md) | 确定性生命周期过期 | 4 | [8](../tutorial/08-lifecycle.md) |
| [15](stage-15.md) | 公开 API 与守链收官 | 0 | [9](../tutorial/09-methodology.md) |


> `journey attempt` 目前为实验性占位；未来将按 CS336 范式重写为测试驱动作业（预置测试与接口桩，实现至转绿，`check` 即评分器）。
