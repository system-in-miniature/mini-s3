# Lab：条件 Compare-and-Swap

[English](../../labs/conditional-cas.md)

运行：

```bash
uv run python labs/lab_conditional_cas.py
```

两个写者先共享当前对象的 ETag，再竞速调用
`put_object(..., if_match=observed)`。输出汇报与调度顺序无关的不变量：

```text
outcomes: ['stored', '412 PreconditionFailed']
one winner: True
one 412: True
final body is complete: True
```

胜者持有 MiniS3 变更锁时改变当前 ETag。败者随后在同一把锁内比较陈旧 token，得到
S3 形态的 412。如果比较和 PUT 是两个独立调用，两个写者可能在任何替换可见之前都
通过检查。
