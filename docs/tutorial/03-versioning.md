# Chapter 3: Versioning, Delete Markers, and the Null Slot

Versioning changes the meaning of both PUT and DELETE. Before it is enabled, an
object has one replaceable public `null` slot. After it is enabled, every PUT
adds a named value and an ordinary DELETE adds a marker rather than destroying
history. Suspending versioning does not restore the original world: named
history remains, while new writes again use a replaceable `null` slot. MiniS3
encodes those rules as a small state machine whose complete behavior fits in
`src/minis3/bucket.py`.

## Learning objectives

By the end of this chapter, you will be able to:

- draw the allowed transitions among `UNVERSIONED`, `ENABLED`, and
  `SUSPENDED`;
- predict PUT and DELETE behavior in each state;
- explain how a delete marker hides bytes without deleting older versions;
- distinguish current GET/DELETE from version-addressed GET/DELETE;
- inspect a flattened version listing and recover a hidden historical value.

## 1. The state machine

`VersioningState` in `src/minis3/bucket.py` defines three states:

```python
class VersioningState(StrEnum):
    UNVERSIONED = "unversioned"
    ENABLED = "enabled"
    SUSPENDED = "suspended"
```

Every new `Bucket` starts unversioned. `Bucket.set_versioning` converts a string
or enum input, then enforces two guards. It rejects any transition back to
`UNVERSIONED` once the bucket has left that state, and it rejects direct
`UNVERSIONED -> SUSPENDED`. The useful transition graph is:

```text
UNVERSIONED ──enable──> ENABLED <──resume── SUSPENDED
                            └──suspend──>───┘
```

Self-transitions are allowed. The missing arrows are as important as the
present ones. “Suspend” stops creation of new named versions; it does not erase
the fact that versioning was enabled or discard named history.

`MiniS3.set_bucket_versioning` in `src/minis3/store.py` performs this transition
on a deep copy, persists the candidate bucket, and only then swaps it into the
live map. Versioning configuration and object history therefore share the same
manifest publication boundary.

## 2. PUT in each state

`Bucket.put` obtains a new sequence and selects the public ID:

```python
version_id = (
    f"v{sequence:08d}"
    if self.versioning is VersioningState.ENABLED
    else NULL_VERSION_ID
)
```

In `ENABLED`, the new `Version` is prepended to all old versions. Every PUT
gets a named ID such as `v00000002`, so each previous value remains
addressable.

In `UNVERSIONED` and `SUSPENDED`, the function removes the old entry whose
public ID is `"null"`, retains named entries, and prepends the new null value.
For a never-versioned bucket there are no named entries, so this behaves like
single-slot replacement. For a suspended bucket it means:

```text
before: [null-old, v00000007, v00000003]
PUT:    [null-new, v00000007, v00000003]
```

The named history survives. Each null value still receives a unique internal
`storage_id`, so crash-atomic publication does not overwrite an immutable
artifact.

## 3. Current GET and version-addressed GET

`Bucket.get` first locates the `ObjectRecord`. Without a `version_id`, it reads
the first entry. If that entry is a `Version`, GET returns it. If it is a
`DeleteMarker`, GET raises `NoSuchKey` even when older data remains.

With a `version_id`, `Bucket.get` scans the history for an exact public ID. A
data version is returned; a marker produces `NoSuchKey`; and a missing ID
produces `NoSuchVersion`. This distinction lets callers tell “the requested
history entry does not exist” from “that entry exists but represents
deletion,” though MiniS3 expresses both through Python exceptions rather than
HTTP headers and XML.

The exact-ID path becomes especially important after a marker hides the current
object. The default GET is absent by design, while
`get_object(..., version_id=old.version_id)` still retrieves retained bytes.

## 4. DELETE is state-dependent

`Bucket.delete` has two modes.

When `version_id` is supplied, it removes only the matching history entry. If
other entries remain, their relative order is unchanged. If the removed entry
was the latest marker, the next data version can become current again. This is
a physical history edit, not creation of another marker.

Without `version_id`, behavior depends on state and history:

- In a truly unversioned bucket with no named history, DELETE removes the
  record and returns `None`.
- In an enabled bucket, DELETE creates a named `DeleteMarker`, prepends it, and
  retains every older entry.
- In a suspended bucket, DELETE creates a `null` marker, replaces any existing
  null entry, and retains named history.

The defensive `has_named_history` branch matters even if public transitions
normally prevent an unversioned bucket from having named history. It avoids
destroying retained values if an aggregate is constructed or recovered in an
unusual state.

`DeleteMarker` in `src/minis3/model.py` contains `version_id`, `storage_id`,
`sequence`, and `created_at`, but no bytes and no ETag. The type boundary
matches its semantic role: it is evidence that the latest state is deletion,
not a zero-byte object.

A useful way to reason about failures is to ask whether an operation changes
visibility, retention, or both. An ordinary enabled DELETE changes visibility
but retains prior data. Deleting an exact historical data version changes
retention and may leave visibility unchanged. Deleting the latest marker
changes both: it removes one retained entry and reveals the next entry. An
unversioned DELETE removes the only retained value and visibility together.
This vocabulary prevents the common mistake of treating every successful
DELETE as physical byte reclamation.

## 5. Listing the hidden history

`MiniS3.list_object_versions` delegates to `list_object_versions` in
`src/minis3/listing.py`. That function sorts keys, walks each newest-first
history, and emits a `ListedVersion` for both data and markers. The first entry
for each key gets `is_latest=True`; markers get `is_delete_marker=True` and
have `etag=None` and `size=None`.

Current listing is different. `list_objects` considers only the first entry
and skips a key whose first entry is a marker. This gives three mutually
consistent observations:

- current GET says `NoSuchKey`;
- current object listing omits the key;
- version listing still shows the marker and retained values.

## 6. Hands-on experiment: delete without destruction

Run the repository lab:

```bash
uv run python labs/lab_versioning.py
```

Measured output:

```text
PUT #1: v00000001 "fedfffb4f154e91a1b00720d80b11387"
PUT #2: v00000002 "564db7a8cce2a309bfdbc66876844f21"
DELETE created marker: v00000003
GET without version-id: NoSuchKey (latest entry is a marker)
Retained history, newest first:
  v00000003: delete-marker, is_latest=true
  v00000002: data, is_latest=false
  v00000001: data, is_latest=false
GET the 'deleted' first version: draft one
```

The counter begins at one, so the deterministic IDs expose operation order.
DELETE consumes the third sequence and publishes a marker. The current lookup
fails, but the final version-addressed GET proves that the first body remains.
This output is not merely a printed story: `tests/test_versioning.py` contains
the exhaustive transition table plus contracts for null replacement, marker
hiding, suspended behavior, and exact-version deletion.

## 7. Compared with Amazon S3

The core versioning transitions align with general-purpose Amazon S3 buckets:
after versioning is enabled, it can be suspended but not returned to the
never-enabled state. Ordinary deletion in an enabled bucket creates a delete
marker, and a request with `versionId` addresses one retained entry. A
replaceable null version can coexist with named history after suspension.
These rows are classified in [the mapping matrix](../mapping.md).

MiniS3 deliberately reduces the surrounding system:

- version IDs are readable counter values, while S3 IDs are opaque;
- one lock serializes calls; there is no distributed metadata concurrency;
- version listing returns all entries in one flattened result and omits S3's
  pagination markers, owner data, timestamp formatting, and encoding options;
- exceptions replace HTTP status, delete-marker headers, and XML bodies;
- there is no object lock, retention policy, legal hold, replication, or IAM.

See the version-ID, version-listing, error, bucket-surface, and concurrency
entries in [Differences from Amazon S3](../DIFFERENCES.md). MiniS3 preserves
the state-machine lesson, not the complete service surface.

## Exercises

### Understanding

1. Why is `SUSPENDED -> UNVERSIONED` forbidden even if the application no
   longer wants new named versions?
2. What observable change occurs when the latest delete marker is removed by
   exact version ID?

??? note "Reference answers"

    1. Suspending does not erase named history or the fact that the bucket has
       version semantics. Returning to never-versioned would make the meaning
       of retained versions and the null slot ambiguous. The supported control
       is suspension, which preserves that history.
    2. The marker is physically removed from the history. If the next entry is
       a data version, it becomes current: default GET and current listing show
       that older value again.

### Hands-on

3. Extend the lab in a copy or inline script: save the returned marker, delete
   it with `version_id=marker.version_id`, and print the now-current body.

   **Acceptance:** default GET prints `draft two`; version listing contains the
   two data versions and no marker; no `src/` file changes.

??? note "Reference answer"

    ```python
    store.delete_object(
        "demo", "report.txt", version_id=marker.version_id
    )
    print(store.get_object("demo", "report.txt").body.decode())
    assert all(
        not item.is_delete_marker
        for item in store.list_object_versions("demo").versions
    )
    ```

4. Produce a proposed test diff, without applying it, for the forbidden direct
   transition from unversioned to suspended.

   **Acceptance:** the proposal uses `pytest.raises(ValueError)`, checks that
   state remains `UNVERSIONED`, and identifies
   `tests/test_versioning.py` as the target.

??? note "Reference answer"

    ```diff
    +def test_cannot_suspend_before_enabling() -> None:
    +    bucket = Bucket("b")
    +    with pytest.raises(ValueError):
    +        bucket.set_versioning("suspended")
    +    assert bucket.versioning is VersioningState.UNVERSIONED
    ```

    The existing parameterized transition test already covers this case; the
    proposed diff is useful as a focused exercise but should not be applied.

## Summary

MiniS3 makes versioning an explicit, irreversible state transition. Enabled
PUTs retain named values; suspension replaces only the null slot; ordinary
versioned DELETE publishes a marker; and exact-version operations edit one
history entry. The result can be absent in the current view while remaining
recoverable in history. Chapter 4 turns from one key's history to the projection
of many flat keys—and explains where the illusion of directories comes from.
