# 自主重建

每个 Stage 都是一节可独立浏览的完整课：先理解当前问题、基本概念与必要性，再按机制板块连接相关文件和关键语句，最后用验证证据和自己的话完成理解闭环。

这是三种学习模式中的浏览器自主学习路径。按主题学习请进入[机制教程](../tutorial/index.md)；需要 CLI 互动请查看 [Agent 带教使用教程](../agent-guided.md)。

如果希望在编辑器里聚焦当前增量，运行 `python journey/tools/build_journey.py study N`，再打开 `../MiniS3-journey-workspace`。

| Stage | 主题 | 新增测试 | 教材章节 |
|---:|---|---:|---:|
| [01](stage-01.md) | 脚手架与对象值 | 3 | [1](../tutorial/01-getting-started.md) |
| [02](stage-02.md) | Bucket 状态与确定性 ID | 1 | [3](../tutorial/03-versioning.md) |
| [03](stage-03.md) | 持久化存储边界 | 1 | [5](../tutorial/05-crash-atomicity.md) |
| [04](stage-04.md) | 对象服务门面 | 15 | [2](../tutorial/02-objects-etag.md) |
| [05](stage-05.md) | 版本历史投影 | 3 | [3](../tutorial/03-versioning.md) |
| [06](stage-06.md) | Listing 与目录幻觉 | 5 | [4](../tutorial/04-listing.md) |
| [07](stage-07.md) | Manifest 发布崩溃矩阵 | 5 | [5](../tutorial/05-crash-atomicity.md) |
| [08](stage-08.md) | 目录 fsync 与启动清理 | 3 | [5](../tutorial/05-crash-atomicity.md) |
| [09](stage-09.md) | Multipart 领域与校验 | 1 | [6](../tutorial/06-multipart.md) |
| [10](stage-10.md) | Multipart 持久暂存 | 1 | [6](../tutorial/06-multipart.md) |
| [11](stage-11.md) | Multipart 原子完成 | 4 | [6](../tutorial/06-multipart.md) |
| [12](stage-12.md) | Multipart 崩溃恢复 | 2 | [6](../tutorial/06-multipart.md) |
| [13](stage-13.md) | 条件请求与 CAS | 4 | [7](../tutorial/07-conditional.md) |
| [14](stage-14.md) | 确定性生命周期过期 | 4 | [8](../tutorial/08-lifecycle.md) |
| [15](stage-15.md) | 公开 API 与守链收官 | 0 | [9](../tutorial/09-methodology.md) |
