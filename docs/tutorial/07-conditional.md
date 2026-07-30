# 07 — Conditional Requests

## Learning objectives

By the end of this chapter, you can:

- evaluate MiniS3's simplified `If-Match` and `If-None-Match` rules;
- distinguish the 304-shaped cache outcome from the 412-shaped precondition failure;
- explain why a conditional mutation must compare and publish under one lock;
- use an ETag as an optimistic concurrency token; and
- identify protocol and ETag cases that the direct API intentionally omits.

## Mechanism: turn an observation into a precondition

An ordinary GET asks, “what is the object now?” A conditional request adds knowledge from an earlier observation: “return it only if it changed,” or “perform this operation only if it is still the version I saw.” This converts an ETag from passive metadata into a control input.

MiniS3 keeps the pure matching rules in `src/minis3/conditional.py`. `etag_matches` splits a comma-separated condition, strips surrounding whitespace, and compares exact strings. A `*` candidate matches whenever a current object exists. Otherwise at least one candidate must equal the current quoted ETag. A missing current object never matches.

The function intentionally does not normalize weak validators, remove quotes, or parse the complete HTTP grammar. Callers pass exact values such as `"9dd4e..."`, including quotes. This small grammar is sufficient to expose the mechanism without pretending to be an HTTP implementation.

Two wrapper functions name different outcomes. `src/minis3/conditional.py::require_if_match` raises `src/minis3/errors.py::PreconditionFailed` when a supplied condition does not match. It represents HTTP 412: the requested operation's prerequisite is false. `require_if_none_match` raises `NotModified` when a supplied condition *does* match. For MiniS3 GET, that represents HTTP 304: the client's cached representation is current, so no body needs to be transferred.

`src/minis3/store.py::MiniS3.get_object` first resolves the requested current or version-addressed `Version` through `Bucket.get`, then evaluates `If-Match`, then `If-None-Match`. The method returns the immutable value only when both supplied conditions allow it. Because this is a direct Python API, exceptions stand in for HTTP status lines and there is no body-less network response.

Conditional writes reveal the deeper concurrency lesson. `MiniS3.put_object` acquires its process-wide `RLock`, deep-copies the bucket, obtains the current visible ETag through `MiniS3._current_etag`, calls `require_if_match`, mutates the candidate with `Bucket.put`, persists it, and swaps the in-memory bucket. The comparison and publication therefore belong to one serialized critical section.

Consider the tempting but incorrect client sequence:

```python
current = store.get_object("b", "k")
if current.etag == expected:
    store.put_object("b", "k", replacement)
```

Each call is individually thread-safe, yet another writer can publish between GET and PUT. Both clients could observe the same old value and both overwrite it. The correct call is `put_object(..., if_match=expected)`, because the store owns the atomic compare-and-swap boundary.

This is optimistic concurrency control. Readers do not acquire a long-lived lease. They read a token, compute independently, and present that token when committing. If the token is stale, the operation fails rather than silently erasing the winner's update. The caller can reread, merge, retry, or report a conflict according to application policy.

`MiniS3.delete_object` uses the same pattern but calls `MiniS3._addressed_etag`. With no version ID it compares the current visible object. With a version ID it compares the exact addressed data version. Missing keys, missing versions, and a current delete marker yield no ETag, so even `If-Match: *` fails. The wildcard means “some current representation exists,” not “unconditionally proceed.”

There is a useful relationship to versioning. In an enabled bucket, a successful conditional PUT creates a new version; the old ETag remains attached to retained history but is no longer the current token. A conditional DELETE without a version ID checks the current data ETag and then creates a delete marker. Later ordinary GET has no current data representation. The retained version may still be fetched by version ID, but that does not make the stale current precondition succeed.

The lock only establishes a single-process linearization order. Persistence still matters: `DiskStorage.persist_bucket` publishes the winning candidate through the atomic manifest rename described in Chapter 5. A losing precondition fails before any artifact or manifest write. A successful caller returns only after local publication completes.

### Read conditions, write conditions, and retry policy

The same matching predicate supports different goals, but callers should name those goals precisely. GET with `If-None-Match` is cache revalidation: a match means the cached bytes may be reused. GET with `If-Match` is a guarded read: a mismatch means the caller's assumed representation is no longer current. PUT or DELETE with `If-Match` is a guarded mutation: a mismatch prevents a lost update. They share ETag syntax without sharing the same success and failure meaning.

A 412 is not an instruction to loop blindly. Suppose two workers read a JSON document, each edits a different field, and one loses CAS. Retrying the old complete replacement with a fresh ETag would erase the winner despite technically satisfying the new precondition. A correct application rereads and recomputes or merges its intended change. MiniS3 intentionally returns the conflict and leaves that domain-specific decision outside the storage layer.

There is also an “uncertain commit” boundary. If a real client loses its connection after sending a conditional write, it may not know whether the service committed it. MiniS3 has no network, so the local method either returns or raises in the same process, but the persistence design still teaches the server side: manifest state is authoritative after recovery. A production adapter would need request identifiers or application-level idempotency where safe retries matter; ETag CAS alone prevents stale replacement but does not identify duplicate requests.

Multiple comma-separated candidates model another useful case. A cache or migration client may accept one of several known representations. `etag_matches` strips whitespace and succeeds when any exact candidate equals current. Yet this remains a deliberately restricted parser: an ETag containing unusual HTTP grammar, a weak tag such as `W/"..."`, or header precedence with date conditions belongs to the future protocol layer, not to an inference from this helper.

## Compared with Amazon S3

Amazon S3 exposes conditional headers over HTTP. `If-None-Match` is commonly used for cache revalidation, and `If-Match` can guard reads and conditional writes. HTTP specifies interactions among methods, dates, entity-tag lists, weak validators, status codes, and response headers. S3 also has service-specific behavior for concurrent conditional operations and supports additional conditions in selected APIs.

MiniS3 preserves the central observable invariants inside a narrower surface: exact quoted ETags and `*`; comma-separated alternatives; 304-shaped `NotModified` for a matching GET `If-None-Match`; 412-shaped `PreconditionFailed` for an unsatisfied `If-Match`; and atomic conditional PUT/DELETE within one process. It has no HTTP adapter, header precedence matrix, request IDs, authentication, distributed conflict protocol, or multi-process locking.

Real S3 ETags are opaque validators from the client's perspective. Encryption, multipart layout, and other service choices mean they are not universally whole-body MD5 hashes. Code should compare the returned ETag, not reconstruct what it assumes the ETag must be. See the [conditional rows and CAS explanation in the mapping](../mapping.md#why-conditional-writes-form-a-cas) and the [Conditions and Concurrency entries in DIFFERENCES](../DIFFERENCES.md#m2-simplifications-and-semantic-departures).

## Hands-on experiment

Run the supplied race:

```bash
uv run python labs/lab_conditional_cas.py
```

Measured output:

```text
outcomes: ['stored', '412 PreconditionFailed']
one winner: True
one 412: True
final body is complete: True
```

The scheduling-dependent fact—whether writer A or writer B wins—is deliberately not printed. The stable invariant is exactly one success and one 412. `Barrier(2)` makes both workers start from the same observed ETag; `MiniS3.put_object` serializes their comparisons. The first changes the current ETag, so the second compares stale state.

Run the focused contracts too:

```bash
uv run pytest -q tests/test_conditional.py
```

They cover matching and mismatching GET conditions, wildcard existence, conditional PUT/DELETE, and the two-writer race.

## Exercises

1. **Understanding.** Why is “thread-safe GET followed by thread-safe PUT” not a compare-and-swap?

??? note "Reference answer"
    Safety of each call does not make the pair indivisible. Another writer may publish after GET releases the lock and before PUT acquires it. `MiniS3.put_object(if_match=...)` evaluates and mutates while holding one lock, so no mutation can interleave.

2. **Understanding.** What do `If-Match: *` and `If-None-Match: *` mean in MiniS3?

??? note "Reference answer"
    `etag_matches("*", current)` is true exactly when a current data ETag exists. Therefore `If-Match: *` requires existence; `If-None-Match: *` on GET raises `NotModified` when the object exists. Neither wildcard matches a missing key or a current delete marker.

3. **Hands-on.** Write `/tmp/cache-check.py` that PUTs `b"value"`, performs GET with `if_none_match=stored.etag`, and prints the caught exception name.

    Acceptance: `uv run python /tmp/cache-check.py` prints `NotModified`; an ordinary GET still returns `b'value'`.

??? note "Reference answer"
    Use `TemporaryDirectory`, import `MiniS3` and `NotModified`, catch only `NotModified`, then call GET again without the condition. The exception is a control outcome, not deletion or corruption. Do not edit `src/`.

4. **Hands-on.** Extend a copy of the CAS lab in `/tmp` to retry the loser once after rereading the new ETag.

    Acceptance: the first round remains one `stored` plus one `412 PreconditionFailed`; the explicit retry with the reread ETag succeeds, and the final body equals the retry body.

??? note "Reference answer"
    Keep the original race unchanged. After the pool closes, read `latest = store.get_object(...)`, then call `put_object(..., if_match=latest.etag)` with a distinct retry body. This demonstrates application-owned conflict policy without weakening the store's CAS boundary.

## Summary

Conditional requests make earlier observations actionable. Pure matching rules provide 304- and 412-shaped outcomes, while the store lock turns `If-Match` plus mutation into a real single-process compare-and-swap. Correct clients treat ETags as opaque returned tokens and choose an explicit retry or conflict policy. The next chapter introduces another policy boundary: time-based lifecycle decisions that are pure and deterministic before they are atomically applied.
