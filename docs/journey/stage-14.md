# Stage 14 · Deterministic lifecycle expiration

### Goal

Separate pure expiration decisions from an explicit mutation tick driven by an injected clock.

??? note "Deliverable files"
    - `src/minis3/__init__.py`
    - `src/minis3/lifecycle.py`
    - `src/minis3/store.py`
    - `tests/test_lifecycle.py`

### The problem at this point

Versions now carry creation times, but nothing expires them. Hiding time reads inside policy or background threads would make boundary behavior nondeterministic and combine “what should happen” with “apply it now.”

### Failure preview

The pure-boundary contract evaluates the same history at time `9.999` and `10.0`. No action is allowed before the threshold; the action appears exactly at it. A hidden wall clock or strict `>` comparison makes this boundary flaky or one tick late.

??? note "File diff: tests/test_lifecycle.py"
    ```diff
    diff --git a/tests/test_lifecycle.py b/tests/test_lifecycle.py
    new file mode 100644
    index 0000000..c413345
    --- /dev/null
    +++ b/tests/test_lifecycle.py
    @@ -0,0 +1,110 @@
    +"""Lifecycle rules are pure decisions applied only by an explicit clocked tick."""
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minis3 import (
    +    ExpirationRule,
    +    LifecycleActionKind,
    +    MiniS3,
    +    NoSuchKey,
    +    NoSuchVersion,
    +    VersioningState,
    +    evaluate_expiration,
    +)
    +
    +
    +class ManualClock:
    +    def __init__(self, now: float = 0.0) -> None:
    +        self.now = now
    +
    +    def __call__(self) -> float:
    +        return self.now
    +
    +
    +def test_rule_evaluation_is_pure_prefix_filtered_and_boundary_inclusive(
    +    tmp_path: Path,
    +) -> None:
    +    clock = ManualClock()
    +    store = MiniS3(tmp_path, clock=clock)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", VersioningState.ENABLED)
    +    store.put_object("b", "logs/old", b"old")
    +    store.put_object("b", "keep/old", b"old")
    +    snapshot = store._buckets["b"].records
    +    rule = ExpirationRule("logs", prefix="logs/", expire_current_after=10)
    +
    +    assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
    +    actions = evaluate_expiration(snapshot, [rule], now=10)
    +
    +    assert [(action.key, action.kind) for action in actions] == [
    +        ("logs/old", LifecycleActionKind.EXPIRE_CURRENT)
    +    ]
    +    assert store.get_object("b", "logs/old").body == b"old"
    +
    +
    +def test_tick_expires_current_to_marker_and_noncurrent_physically(
    +    tmp_path: Path,
    +) -> None:
    +    clock = ManualClock()
    +    store = MiniS3(tmp_path, clock=clock)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    old = store.put_object("b", "k", b"old")
    +    clock.now = 5
    +    current = store.put_object("b", "k", b"current")
    +    rule = ExpirationRule(
    +        "expire",
    +        expire_current_after=10,
    +        expire_noncurrent_after=12,
    +    )
    +
    +    clock.now = 12
    +    first_actions = store.lifecycle_tick("b", [rule])
    +    assert [action.kind for action in first_actions] == [
    +        LifecycleActionKind.EXPIRE_NONCURRENT
    +    ]
    +    with pytest.raises(NoSuchVersion):
    +        store.get_object("b", "k", version_id=old.version_id)
    +    assert store.get_object("b", "k") == current
    +
    +    clock.now = 15
    +    second_actions = store.lifecycle_tick("b", [rule])
    +    assert [action.kind for action in second_actions] == [
    +        LifecycleActionKind.EXPIRE_CURRENT
    +    ]
    +    with pytest.raises(NoSuchKey):
    +        store.get_object("b", "k")
    +    history = store.list_object_versions("b").versions
    +    assert history[0].is_delete_marker is True
    +    assert history[1].version_id == current.version_id
    +
    +
    +def test_tick_uses_injected_time_and_persists_timestamps_across_restart(
    +    tmp_path: Path,
    +) -> None:
    +    clock = ManualClock(100)
    +    store = MiniS3(tmp_path, clock=clock)
    +    store.create_bucket("b")
    +    store.set_bucket_versioning("b", "enabled")
    +    version = store.put_object("b", "k", b"value")
    +    assert version.created_at == 100
    +
    +    reopened_clock = ManualClock(109)
    +    reopened = MiniS3(tmp_path, clock=reopened_clock)
    +    rule = ExpirationRule("ten-seconds", expire_current_after=10)
    +    assert reopened.lifecycle_tick("b", [rule]) == ()
    +
    +    reopened_clock.now = 110
    +    assert reopened.lifecycle_tick("b", [rule])[0].kind is (
    +        LifecycleActionKind.EXPIRE_CURRENT
    +    )
    +
    +
    +def test_expiration_rule_rejects_empty_or_negative_policy() -> None:
    +    with pytest.raises(ValueError):
    +        ExpirationRule("empty")
    +    with pytest.raises(ValueError):
    +        ExpirationRule("negative", expire_current_after=-1)
    +
    ```

**What this test locks**

Four contracts cover pure filtering/boundaries, current versus noncurrent transitions, injected time/restart, and invalid rules.

**How it constructs the counterexample**

`ManualClock` lets tests advance time deliberately and prove persisted timestamps rather than waiting on wall time.

**Key test statement**

```python
assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
```

**What a failure means**

This is the just-before boundary. Paired with the `10.0` assertion, it proves inclusion precisely rather than merely testing an obviously old object.

### Basic concepts

Policy evaluation is a pure calculation from immutable history, rules, and explicit `now`. It emits `LifecycleAction` decisions. `lifecycle_tick` is the separate mutation boundary that applies those decisions under the service lock and persists only when state changes.

Expiring a current data version creates a delete marker so older history stays hidden. Expiring a noncurrent version physically removes that addressed historical item.

### Why this mechanism is necessary

Pure evaluation can be reasoned about and repeated without side effects. An injected clock makes tests and replay deterministic. An explicit tick also makes it clear when durability and locking obligations begin.

### Runtime mental model

The caller invokes `lifecycle_tick` with rules. The service captures injected time, deep-copies the Bucket, calls `evaluate_expiration`, applies each action through Bucket deletion semantics, persists the candidate if actions exist, swaps it, and returns the action list.

### Mechanism blocks

#### Pure lifecycle policy

Select deterministic expiration actions from histories, ordered rules, and an explicit time without mutating state.

??? note "File diff: src/minis3/lifecycle.py"
    ```diff
    diff --git a/src/minis3/lifecycle.py b/src/minis3/lifecycle.py
    new file mode 100644
    index 0000000..ca0c3f0
    --- /dev/null
    +++ b/src/minis3/lifecycle.py
    @@ -0,0 +1,103 @@
    +"""Pure lifecycle expiration decisions for an explicit manual tick.
    +
    +Evaluation reads an immutable-style snapshot and returns actions; it never
    +mutates records or reads a clock. The service injects ``now`` and applies the
    +actions only when the caller explicitly requests a tick.
    +"""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from enum import StrEnum
    +
    +from .model import ObjectRecord, Version
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ExpirationRule:
    +    """Age thresholds for matching current and noncurrent data versions."""
    +
    +    rule_id: str
    +    prefix: str = ""
    +    expire_current_after: float | None = None
    +    expire_noncurrent_after: float | None = None
    +
    +    def __post_init__(self) -> None:
    +        thresholds = (self.expire_current_after, self.expire_noncurrent_after)
    +        if all(value is None for value in thresholds):
    +            raise ValueError("an expiration rule needs at least one threshold")
    +        if any(value is not None and value < 0 for value in thresholds):
    +            raise ValueError("expiration ages must be non-negative")
    +
    +
    +class LifecycleActionKind(StrEnum):
    +    """The two deliberately small M2 lifecycle transitions."""
    +
    +    EXPIRE_CURRENT = "expire_current"
    +    EXPIRE_NONCURRENT = "expire_noncurrent"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LifecycleAction:
    +    """One deterministic mutation selected by a named rule."""
    +
    +    rule_id: str
    +    key: str
    +    version_id: str
    +    kind: LifecycleActionKind
    +
    +
    +def _old_enough(created_at: float, threshold: float | None, now: float) -> bool:
    +    return threshold is not None and now - created_at >= threshold
    +
    +
    +def evaluate_expiration(
    +    records: dict[str, ObjectRecord],
    +    rules: list[ExpirationRule] | tuple[ExpirationRule, ...],
    +    *,
    +    now: float,
    +) -> tuple[LifecycleAction, ...]:
    +    """Return de-duplicated actions without changing the supplied records."""
    +
    +    actions: list[LifecycleAction] = []
    +    selected: set[tuple[str, str, LifecycleActionKind]] = set()
    +    for key in sorted(records):
    +        record = records[key]
    +        if not record.versions:
    +            continue
    +        for rule in rules:
    +            if not key.startswith(rule.prefix):
    +                continue
    +            current = record.versions[0]
    +            identity = (key, current.version_id, LifecycleActionKind.EXPIRE_CURRENT)
    +            if (
    +                isinstance(current, Version)
    +                and identity not in selected
    +                and _old_enough(
    +                    current.created_at, rule.expire_current_after, now
    +                )
    +            ):
    +                selected.add(identity)
    +                actions.append(
    +                    LifecycleAction(rule.rule_id, key, current.version_id, identity[2])
    +                )
    +            for version in record.versions[1:]:
    +                identity = (
    +                    key,
    +                    version.version_id,
    +                    LifecycleActionKind.EXPIRE_NONCURRENT,
    +                )
    +                if (
    +                    isinstance(version, Version)
    +                    and identity not in selected
    +                    and _old_enough(
    +                        version.created_at, rule.expire_noncurrent_after, now
    +                    )
    +                ):
    +                    selected.add(identity)
    +                    actions.append(
    +                        LifecycleAction(
    +                            rule.rule_id, key, version.version_id, identity[2]
    +                        )
    +                    )
    +    return tuple(actions)
    ```

**What it is and why it appears**

This pure policy module defines expiration rules, action values, and decision evaluation.

**Runtime role**

It reads histories and returns what should change; it never calls storage or mutates Bucket records.

**Key code**

```python
return threshold is not None and now - created_at >= threshold
```

**Statement understanding**

`>=` makes the policy boundary inclusive and deterministic. `None` means that category has no expiration rule, not age zero.

#### Clocked lifecycle application

Apply selected actions through existing version semantics under a lock, then persist only the resulting changed Bucket.

??? note "File diff: src/minis3/store.py"
    ```diff
    diff --git a/src/minis3/store.py b/src/minis3/store.py
    index e47e1ac..c2bdc5b 100644
    --- a/src/minis3/store.py
    +++ b/src/minis3/store.py
    @@ -1,4 +1,9 @@
    -"""Public service facade joining buckets, object state, and list projections."""
    +"""Public service facade joining buckets, object state, and list projections.
    +
    +This initial service boundary deliberately resembles an SDK rather than an HTTP
    +server. A future thin protocol adapter can translate these domain values and
    +errors without taking ownership of storage semantics.
    +"""

     from __future__ import annotations

    @@ -8,10 +13,27 @@ from pathlib import Path
     from threading import RLock
     from time import time

    -from .conditional import require_if_match, require_if_none_match
     from .bucket import Bucket, SequenceCounter, VersioningState
    -from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket, NoSuchKey, NoSuchVersion
    -from .listing import ListObjectsResult, ListObjectVersionsResult, list_object_versions, list_objects
    +from .conditional import require_if_match, require_if_none_match
    +from .errors import (
    +    BucketAlreadyExists,
    +    BucketNotEmpty,
    +    NoSuchBucket,
    +    NoSuchKey,
    +    NoSuchVersion,
    +)
    +from .lifecycle import (
    +    ExpirationRule,
    +    LifecycleAction,
    +    LifecycleActionKind,
    +    evaluate_expiration,
    +)
    +from .listing import (
    +    ListObjectsResult,
    +    ListObjectVersionsResult,
    +    list_object_versions,
    +    list_objects,
    +)
     from .model import ObjectVersion, Version
     from .multipart import (
         MAX_PART_NUMBER,
    @@ -50,7 +72,6 @@ class MiniS3:
                 ensure(maximum_sequence + 1)
             self._lock = RLock()

    -
         def create_bucket(self, name: str) -> None:
             with self._lock:
                 if name in self._buckets:
    @@ -59,7 +80,6 @@ class MiniS3:
                 self._storage.create_bucket(bucket)
                 self._buckets[name] = bucket

    -
         def delete_bucket(self, name: str) -> None:
             with self._lock:
                 bucket = self._bucket(name)
    @@ -68,7 +88,6 @@ class MiniS3:
                 self._storage.delete_bucket(name)
                 del self._buckets[name]

    -
         def set_bucket_versioning(
             self, name: str, state: VersioningState | str
         ) -> None:
    @@ -78,7 +97,6 @@ class MiniS3:
                 self._storage.persist_bucket(candidate)
                 self._buckets[name] = candidate

    -
         def put_object(
             self,
             bucket: str,
    @@ -97,7 +115,6 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    -
         def get_object(
             self,
             bucket: str,
    @@ -113,7 +130,6 @@ class MiniS3:
                 require_if_none_match(result.etag, if_none_match)
                 return result

    -
         def head_object(
             self, bucket: str, key: str, *, version_id: str | None = None
         ) -> Version:
    @@ -121,7 +137,6 @@ class MiniS3:

             return self.get_object(bucket, key, version_id=version_id)

    -
         def delete_object(
             self,
             bucket: str,
    @@ -142,7 +157,6 @@ class MiniS3:
                 self._buckets[bucket] = candidate
                 return result

    -
         def list_objects(
             self,
             bucket: str,
    @@ -161,14 +175,12 @@ class MiniS3:
                     continuation_token=continuation_token,
                 )

    -
         def list_object_versions(
             self, bucket: str, *, prefix: str = ""
         ) -> ListObjectVersionsResult:
             with self._lock:
                 return list_object_versions(self._bucket(bucket).records, prefix=prefix)

    -
         def create_multipart_upload(
             self, bucket: str, key: str
         ) -> MultipartUpload:
    @@ -187,7 +199,6 @@ class MiniS3:
                 self._storage.create_multipart_upload(upload)
                 return upload

    -
         def upload_part(
             self,
             bucket: str,
    @@ -206,7 +217,6 @@ class MiniS3:
                 self._storage.write_multipart_part(bucket, key, upload_id, part)
                 return part.receipt

    -
         def complete_multipart_upload(
             self,
             bucket: str,
    @@ -239,7 +249,6 @@ class MiniS3:
                 self._storage.remove_multipart_upload(bucket, key, upload_id)
                 return result

    -
         def abort_multipart_upload(
             self, bucket: str, key: str, upload_id: str
         ) -> None:
    @@ -249,6 +258,37 @@ class MiniS3:
                 self._bucket(bucket)
                 self._storage.remove_multipart_upload(bucket, key, upload_id)

    +    def lifecycle_tick(
    +        self,
    +        bucket: str,
    +        rules: list[ExpirationRule] | tuple[ExpirationRule, ...],
    +    ) -> tuple[LifecycleAction, ...]:
    +        """Evaluate at the injected time and atomically apply selected actions."""
    +
    +        with self._lock:
    +            candidate = deepcopy(self._bucket(bucket))
    +            now = self._clock()
    +            actions = evaluate_expiration(
    +                candidate.records, rules, now=now
    +            )
    +            for action in actions:
    +                if action.kind is LifecycleActionKind.EXPIRE_CURRENT:
    +                    current = candidate.records[action.key].versions[0]
    +                    if current.version_id == action.version_id:
    +                        candidate.delete(
    +                            action.key, self._counter, now=now
    +                        )
    +                else:
    +                    candidate.delete(
    +                        action.key,
    +                        self._counter,
    +                        action.version_id,
    +                        now=now,
    +                    )
    +            if actions:
    +                self._storage.persist_bucket(candidate)
    +                self._buckets[bucket] = candidate
    +            return actions

         @staticmethod
         def _current_etag(bucket: Bucket, key: str) -> str | None:
    @@ -257,7 +297,6 @@ class MiniS3:
             except NoSuchKey:
                 return None

    -
         @staticmethod
         def _addressed_etag(
             bucket: Bucket, key: str, version_id: str | None
    @@ -267,10 +306,8 @@ class MiniS3:
             except (NoSuchKey, NoSuchVersion):
                 return None

    -
         def _bucket(self, name: str) -> Bucket:
             try:
                 return self._buckets[name]
             except KeyError as exc:
                 raise NoSuchBucket(name) from exc
    -
    ```

**What it is and why it appears**

The service adds the explicit tick that converts pure actions into durable state transitions.

**Runtime role**

It supplies one time value and stable snapshot under the lock, then reuses Bucket deletion and candidate publication.

**Key code**

```python
self._storage.persist_bucket(candidate)
```

**Statement understanding**

Policy output alone changes nothing. Persisting the candidate is what makes an applied expiration survive restart; no-action ticks avoid needless publication.

#### Public export wiring

Expose lifecycle policy values without duplicating their policy or execution explanation.

??? note "Supporting file diffs (1 file)"
    **`src/minis3/__init__.py`**

    ```diff
    diff --git a/src/minis3/__init__.py b/src/minis3/__init__.py
    index 3f6e582..36bc1f3 100644
    --- a/src/minis3/__init__.py
    +++ b/src/minis3/__init__.py
    @@ -1,10 +1,34 @@
     """Public API for the MiniS3 teaching implementation."""
    -from .errors import BucketAlreadyExists, BucketNotEmpty, InvalidContinuationToken, MiniS3Error, NoSuchBucket, NoSuchKey, NoSuchVersion
    +
    +from .errors import (
    +    BucketAlreadyExists,
    +    BucketNotEmpty,
    +    EntityTooSmall,
    +    InvalidContinuationToken,
    +    InvalidPart,
    +    InvalidPartOrder,
    +    MiniS3Error,
    +    NoSuchBucket,
    +    NoSuchKey,
    +    NoSuchUpload,
    +    NoSuchVersion,
    +    NotModified,
    +    PreconditionFailed,
    +)
     from .bucket import SequenceCounter, VersioningState
    +from .listing import (
    +    ListedObject,
    +    ListedVersion,
    +    ListObjectsResult,
    +    ListObjectVersionsResult,
    +)
     from .model import DeleteMarker, ObjectRecord, Version, content_etag
    +from .lifecycle import (
    +    ExpirationRule,
    +    LifecycleAction,
    +    LifecycleActionKind,
    +    evaluate_expiration,
    +)
    +from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
     from .store import MiniS3
     from .storage import InjectedCrash
    -from .listing import ListedObject, ListedVersion, ListObjectsResult, ListObjectVersionsResult
    -from .errors import EntityTooSmall, InvalidPart, InvalidPartOrder, NoSuchUpload
    -from .multipart import MIN_PART_SIZE, MultipartPart, MultipartUpload
    -from .errors import NotModified, PreconditionFailed
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/14-lifecycle-tick/tests.txt)`. The cases prove pure policy, explicit mutation, time injection, restart persistence, and rule validation.

### Durable takeaways

Decide purely, mutate explicitly, inject time, and persist only applied actions. Current expiration creates a marker; noncurrent expiration removes one historical version.

### Explain it in your own words

MiniS3 separates lifecycle policy from execution. A pure function decides actions from history, rules, and an explicit clock; a locked tick applies those actions through existing version semantics and publishes the resulting Bucket so time-based behavior remains deterministic and recoverable.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-s3/blob/main/docs/tutorial/08-lifecycle.md)

[Compare this stage on GitHub](https://github.com/system-in-miniature/mini-s3/compare/stage-13...stage-14)

After finishing, use `git checkout stage-14` to compare your result.

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-s3/blob/main/journey/stages/14-lifecycle-tick/stage.patch)
