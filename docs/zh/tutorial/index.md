# MiniS3：九章读懂一个对象存储

本书从一次直接 API 调用出发，逐步把 MiniS3 展开为一份对象存储语义与本地持久性的
紧凑教材。请按顺序阅读：每章都依赖前章建立的词汇和机制，且每个机制论断都会回到
`src/minis3/` 下的具体函数。

MiniS3 是教学内核，不是 Amazon S3 替代品。阅读时请把
[映射矩阵](../mapping.md)和[明确差异](../DIFFERENCES.md)放在手边：它们把等价的
可观察不变量、刻意简化和未实现的生产能力分开。

## 如何使用本书

1. 在仓库根目录使用 `uv run` 执行命令。
2. 先让章节说明源码函数的角色，再阅读具名函数，不要一开始盲读整个文件。
3. 把自己的实测输出与实验输出块逐行比较。
4. 先完成练习，再展开折叠参考答案。
5. 除非题目要求提出 diff，否则练习变化保持在 `src/` 之外；教程本身不修改实现。

## 章节目录

1. **[认识 MiniS3](01-getting-started.md)** —— 准备环境，创建第一个桶与对象，
   理解直接 API 边界，并建立全书地图。
2. **[对象、扁平 Key 与 ETag](02-objects-etag.md)** —— 区分不透明 key、不可变值、
   公开版本 ID、内部存储 ID 与单次 PUT 的 MD5 ETag。
3. **[版本化、删除标记与 Null 槽](03-versioning.md)** —— 跟踪不可逆版本状态机，
   恢复被遮住的历史，并区分普通删除与按版本删除。
4. **[List 与目录幻觉](04-listing.md)** —— 从扁平字符串推导 content 和 common
   prefix，为投影分页，并定义强一致边界。
5. **[崩溃原子性与 Manifest 发布](05-crash-atomicity.md)** —— 跟踪不可变
   artifact、文件与目录 fsync、原子 manifest 替换、崩溃注入和启动清理。
6. **[分片上传](06-multipart.md)** —— 私有暂存 part，校验完成清单，原子发布，并
   推导 multipart ETag。
7. **[条件请求与 CAS](07-conditional.md)** —— 把 `If-Match`/`If-None-Match`
   转化为缓存验证与串行化 compare-and-swap。
8. **[生命周期过期](08-lifecycle.md)** —— 使用注入时钟和显式 tick，对当前与
   noncurrent 版本执行纯过期规则。
9. **[方法论与边界](09-methodology.md)** —— 把实验连接到 System-in-Miniature
   方法，并识别仓库之外的分布式、安全和运维机制。

## 参考资料架

若需要最短运行路径，请看[快速开始](../index.md)；若需要等价性分类，请看
[机制映射](../mapping.md)；若按实验导航，请看 [Lab 指南](../labs-guide.md)；涉及
生产对照时，请随时检查[与 Amazon S3 的差异](../DIFFERENCES.md)。
