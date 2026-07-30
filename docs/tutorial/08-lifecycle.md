# 08 — Lifecycle Expiration

## Learning objectives

By the end of this chapter, you can:

- separate pure lifecycle selection from durable mutation;
- explain prefix filtering, age thresholds, and inclusive boundary behavior;
- distinguish expiration of current and noncurrent versions;
- predict how versioning changes the result of current expiration; and
- state where MiniS3's manual deterministic tick differs from Amazon S3 lifecycle.

## Mechanism: decide first, apply second

Object stores accumulate data. Lifecycle rules express retention policy: when an object reaches an age, expire it or move it to another storage class. MiniS3 implements only expiration, but it uses that small surface to teach an important design: policy evaluation should be deterministic and inspectable before storage mutation begins.

`src/minis3/lifecycle.py::ExpirationRule` contains a stable rule ID, a key prefix, and optional thresholds for current and noncurrent data versions. `__post_init__` rejects a rule with no threshold and rejects negative ages. Zero is valid: it means an eligible version is old enough at the evaluation instant.

The rule is deliberately a value passed to a tick, not durable bucket configuration. It does not read the clock. `src/minis3/lifecycle.py::_old_enough` receives all three inputs and uses:

```python
return threshold is not None and now - created_at >= threshold
```

The `>=` makes the boundary inclusive. A version created at time 0 with threshold 10 is selected at exactly 10, not just after 10. Injecting `now` avoids flaky sleeps and makes that contract testable.

`src/minis3/lifecycle.py::evaluate_expiration` accepts a record snapshot, rules, and explicit `now`. It returns an immutable tuple of `LifecycleAction` values without changing the records. Keys are traversed in sorted order, making output deterministic. A rule applies only when `key.startswith(rule.prefix)`.

For each record, `versions[0]` is current. Current expiration is considered only when that entry is a `src/minis3/model.py::Version`; a `DeleteMarker` is not selected. Historical entries in `versions[1:]` are considered for noncurrent expiration, again only if they are data versions. MiniS3 does not expire delete markers.

Actions carry the `rule_id`, key, exact version ID, and a `LifecycleActionKind`: `EXPIRE_CURRENT` or `EXPIRE_NONCURRENT`. A `selected` set deduplicates identical key/version/kind decisions when overlapping rules match. The first matching rule in caller order supplies the reported rule ID. Thus evaluation is stable for a fixed record snapshot, rule order, and `now`.

Why return actions instead of deleting immediately? The pure phase can be unit-tested without disk or time. More importantly, selection and application have different responsibilities. Selection answers policy questions; the service owns synchronization, versioning transitions, and durable publication.

`src/minis3/store.py::MiniS3.lifecycle_tick` supplies that second phase. It acquires the store's `RLock`, deep-copies the bucket, samples the injected clock once, and calls `evaluate_expiration` on the candidate. Every decision in one tick therefore uses the same time and a stable bucket view.

For `EXPIRE_NONCURRENT`, the service calls `src/minis3/bucket.py::Bucket.delete` with the exact version ID. Version-addressed deletion physically removes that historical entry from the record. For `EXPIRE_CURRENT`, it first confirms that the selected version is still current and calls `Bucket.delete` without a version ID.

That last call is intentionally versioning-aware. In an enabled bucket, ordinary current deletion creates a new `DeleteMarker`. The older bytes are hidden but retained until a noncurrent rule removes them. In an unversioned bucket, deletion physically removes the null version. In a suspended bucket, `Bucket.delete` follows the suspended/null-version rules described in Chapter 3. Lifecycle does not bypass the bucket state machine.

After all actions are applied to the candidate, the tick calls `src/minis3/storage/disk.py::DiskStorage.persist_bucket` once and replaces the live in-memory bucket. The whole action set is therefore one local bucket publication, not a sequence of partially visible deletes. If no actions were selected, it performs no manifest write.

Creation time comes from the injected service clock. `MiniS3.put_object` passes `self._clock()` into `Bucket.put`; multipart completion does the same. `src/minis3/storage/disk.py::DiskStorage._write_artifact` persists `created_at`, and `_load_artifact` restores it, so a restart does not reset object age.

There are two honest subtleties. First, MiniS3 measures a noncurrent version's age from its original creation time. Amazon S3's `NoncurrentDays` is based on when a version becomes noncurrent. MiniS3 does not persist that transition timestamp. Second, nothing runs automatically. A version may remain older than its threshold indefinitely until the application calls `lifecycle_tick`.

### Overlapping rules and repeated ticks

Lifecycle evaluation may receive overlapping rules, such as a broad `logs/` rule and a narrower `logs/audit/` rule. `evaluate_expiration` traverses rules in caller order but deduplicates the same key, version, and action kind. The action reports the first rule that selected it. This keeps one tick from attempting the same deletion twice, but MiniS3 does not implement production conflict resolution among different action types because expiration is its only action family.

Repeated ticks are naturally state-based. After a noncurrent version is removed, it is absent from the next snapshot and cannot be selected again. After current expiration creates a delete marker, that marker is not a `Version`, so another current-expiration tick does not stack markers for the same already-hidden data. If an older data version remains behind the marker, it occupies a historical position and may later match a noncurrent rule. These properties arise from `ObjectRecord` state plus type checks rather than a separate “rule already ran” database.

One detail deserves operational attention: `lifecycle_tick` returns the actions selected before persistence. In normal completion, those actions were also applied and published. If storage raises, the method does not return a success tuple, and callers must not record the policy as completed merely because pure evaluation would select it. A background implementation would need retry state, metrics, rate limits, and crash-safe work ownership; the manual synchronous API avoids claiming those mechanisms.

## Compared with Amazon S3

Amazon S3 stores lifecycle configuration on the bucket and evaluates it as a managed background service. Rules can filter by prefix, tags, object size, or combinations. Actions include current expiration, noncurrent expiration, delete-marker cleanup, aborting incomplete multipart uploads, and transitions among storage classes. Execution timing is service-managed and may not occur at the exact instant an age boundary is crossed.

MiniS3 implements only prefix-and-age expiration for data versions. Its manual tick is deterministic, synchronous, and atomic within one process. It has no scheduler, durable rule configuration, tags, size filters, transitions, fees, minimum-storage-duration model, delete-marker cleanup, or incomplete-upload expiration. Its numeric clock also omits S3 date rounding and HTTP Last-Modified formatting.

The useful equivalence is narrower: current expiration in a versioned bucket uses a delete marker; noncurrent expiration removes an addressed historical data version; and unversioned current expiration removes the object. The [Expiration tick mapping row](../mapping.md) classifies this as an intentional simplification. The [Lifecycle and Time entries in DIFFERENCES](../DIFFERENCES.md#m2-simplifications-and-semantic-departures) document the noncurrent-age and manual-scheduling departures.

## Hands-on experiment

Run this exact script from the repository root:

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minis3 import ExpirationRule, MiniS3, NoSuchKey

class Clock:
    now = 0.0
    def __call__(self): return self.now

with TemporaryDirectory() as root:
    clock = Clock()
    store = MiniS3(root, clock=clock)
    store.create_bucket("demo")
    store.set_bucket_versioning("demo", "enabled")
    store.put_object("demo", "logs/app.log", b"old")
    clock.now = 5
    store.put_object("demo", "logs/app.log", b"current")
    rule = ExpirationRule("logs", prefix="logs/",
        expire_current_after=10, expire_noncurrent_after=12)
    clock.now = 12
    print([(a.kind.value, a.version_id)
           for a in store.lifecycle_tick("demo", [rule])])
    clock.now = 15
    print([(a.kind.value, a.version_id)
           for a in store.lifecycle_tick("demo", [rule])])
    try:
        store.get_object("demo", "logs/app.log")
    except NoSuchKey:
        print("current GET: NoSuchKey")
    print([(v.version_id, v.is_delete_marker)
           for v in store.list_object_versions("demo").versions])
PY
```

Measured output:

```text
[('expire_noncurrent', 'v00000001')]
[('expire_current', 'v00000002')]
current GET: NoSuchKey
[('v00000003', True), ('v00000002', False)]
```

At time 12, the old version is 12 units old and is removed as noncurrent; the current version is only 7 units old. At time 15, the current version reaches its inclusive threshold of 10. Expiring it creates marker `v00000003`, so ordinary GET fails while version `v00000002` remains addressable.

Pin the edge cases with:

```bash
uv run pytest -q tests/test_lifecycle.py
```

## Exercises

1. **Understanding.** Why does `evaluate_expiration` receive `now` instead of calling `time.time()`?

??? note "Reference answer"
    An explicit input makes the decision pure, deterministic, and testable at exact boundaries. `lifecycle_tick` samples the injected clock once, so every rule in a tick sees the same instant. A hidden clock read could vary during evaluation and require sleeps in tests.

2. **Understanding.** Why does current expiration create a marker in an enabled bucket but noncurrent expiration physically removes a version?

??? note "Reference answer"
    Current expiration uses the bucket's ordinary unversioned-address delete transition, which preserves versioning semantics by adding a delete marker. A noncurrent action already names one historical version ID, so `Bucket.delete` removes that exact entry.

3. **Hands-on.** Copy the inline experiment to `/tmp/lifecycle-boundary.py` and run ticks at `14.999` and `15`.

    Acceptance: the current-expiration action tuple is empty at `14.999` and contains one `expire_current` action at `15`.

??? note "Reference answer"
    Keep the current version's creation time at 5 and threshold at 10. Set `clock.now = 14.999`, print the first tick, then set it to 15 and print again. The `>=` comparison explains the transition. Do not edit `src/`.

4. **Hands-on.** Add a `keep/` object to the `/tmp` script while retaining the `logs/` rule.

    Acceptance: after both ticks, `get_object("demo", "keep/item")` still returns its body and no action names that key.

??? note "Reference answer"
    PUT `keep/item` before advancing the clock. Because `evaluate_expiration` requires `key.startswith("logs/")`, its age is irrelevant to this rule. Print action keys and the surviving body as evidence.

## Summary

MiniS3 lifecycle is a two-phase policy engine: pure, deterministic selection produces explicit actions, then one locked service operation applies them through the normal versioning and persistence machinery. That structure makes time, version identity, and atomicity visible while keeping the production gap explicit. The final chapter uses these same habits—small mechanisms, executable contracts, and named boundaries—to show how to continue from a teaching kernel toward real object-storage systems.
