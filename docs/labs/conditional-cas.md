# Lab: Conditional Compare-and-Swap

[中文版](../zh/labs/conditional-cas.md)

Run:

```bash
uv run python labs/lab_conditional_cas.py
```

Both writers first share the current object's ETag, then race to call
`put_object(..., if_match=observed)`. The output reports the scheduling-free
invariant:

```text
outcomes: ['stored', '412 PreconditionFailed']
one winner: True
one 412: True
final body is complete: True
```

The winner changes the current ETag while holding MiniS3's mutation lock. The
loser then compares its stale token under the same lock and receives the
S3-shaped 412 outcome. If the comparison and PUT were separate calls, both
writers could pass the check before either replacement became visible.
