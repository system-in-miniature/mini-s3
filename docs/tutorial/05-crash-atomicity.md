# Chapter 5: Crash Atomicity and Manifest Publication

A write that returns a complete object during normal execution can still be
wrong if process death leaves half metadata, half bytes, or a directory entry
that was never durably recorded. MiniS3 makes local crash atomicity visible
with a small filesystem protocol: create immutable artifacts, flush files and
directory entries, publish one manifest by atomic rename, and recover using
only that manifest. The promised outcome is old complete state or new complete
state—not partial state—under the documented POSIX assumptions.

## Learning objectives

By the end of this chapter, you will be able to:

- describe MiniS3's bucket, object-artifact, and manifest disk layout;
- explain the ordering `temporary write -> file fsync -> rename -> directory
  fsync`;
- identify `manifest.json` rename as the visibility linearization point;
- predict recovery before and after the manifest publication hook;
- state exactly what local crash atomicity does and does not guarantee.

## 1. Disk layout separates data from visibility

`DiskStorage` in `src/minis3/storage/disk.py` owns this layout:

```text
buckets/<encoded-bucket>/
  manifest.json
  objects/<sha256-key>/<storage-id>.json
  objects/<sha256-key>/<storage-id>.data
  uploads/...
```

Bucket names are URL-safe-base64 encoded by `_encoded_name`. Object keys are
hashed by `_object_directory`, so path-shaped or hostile-looking key strings
never become filesystem paths. The original key remains inside metadata and
the manifest; SHA-256 here is an addressing convenience, not object integrity
proof.

Each data version has a `.data` file and a `.json` metadata file. A delete
marker needs only metadata. Files are named with the unique internal
`storage_id`, not the replaceable public `version_id`. As Chapter 2 showed,
this lets repeated public `null` values coexist temporarily as distinct
immutable artifacts during a commit.

`manifest.json` contains the bucket name, versioning state, and, for each key,
the ordered list of referenced storage IDs. It is the authoritative reachability
map. Artifact existence alone does not make a value visible.

## 2. Publishing one file durably

The reusable primitive is `atomic_write` in
`src/minis3/storage/atomic.py`:

```python
with temporary.open("wb") as handle:
    handle.write(payload)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, path)
fsync_directory(path.parent)
```

Writing a sibling temporary file prevents readers of the final name from
seeing partially written bytes. `handle.flush()` moves Python's buffered bytes
to the operating system. `os.fsync(handle.fileno())` asks the filesystem to
persist file data and metadata required for the file. `os.replace` atomically
switches the directory entry from old final file to new complete file on the
same filesystem. Finally, `fsync_directory` persists that directory-entry
change.

File fsync and directory fsync solve different problems. A durable file is not
enough if the directory entry naming it disappears after power loss.
Conversely, a durable name is not enough if the named bytes were never
flushed. The protocol needs both, in order.

`durable_mkdir` walks upward to discover missing directories, creates them, and
fsyncs each newly created entry's parent from the outside inward. This closes a
subtle hole: a perfectly flushed object file is not recoverable if a newly
created ancestor directory itself was never made durable.

## 3. Artifact first, manifest last

`DiskStorage.persist_bucket` is the commit protocol. It iterates over every
version referenced by the candidate bucket and calls `_write_artifact`.
Existing metadata paths are skipped because artifacts are immutable. New data
versions get their `.data` file atomically written, then metadata is atomically
written.

Only after every referenced artifact exists does `persist_bucket` execute:

```python
self._inject("before_manifest_publish")
atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
self._inject("after_manifest_publish")
self._clean_bucket(directory, bucket)
```

The atomic replacement of `manifest.json` is the linearization point. Before
it, the old manifest references only old complete artifacts. New files may be
durable but unreachable. After it, the new manifest references only artifacts
that were durably written first. Cleanup is deliberately after publication:
removing old artifacts before the manifest switches could break the old state.

The crash injector names both sides of this boundary. It is called after the
new artifacts are durable but before the manifest switch, and again after the
switch. Raising `InjectedCrash` simulates abrupt process death without adding
production control flow to the mechanism.

## 4. Service-level candidate publication

The filesystem protocol is paired with `MiniS3.put_object` in
`src/minis3/store.py`. Under the process lock, the service deep-copies the
bucket, changes the copy, calls `persist_bucket`, then assigns the copy to
`self._buckets`.

This order aligns two visibility domains:

- If disk persistence fails before manifest publication, the running process
  still holds the old bucket.
- If the manifest publishes successfully, the service installs the matching
  candidate in memory.

An injected crash after manifest publication interrupts before the in-memory
assignment, but that process is modeled as dead. A new `MiniS3` instance
recovers the new state from the published manifest. Crash tests must therefore
reopen the store; continuing to use the deliberately crashed instance would
not model process death faithfully.

## 5. Startup recovery

`DiskStorage.load_buckets` scans the bucket root. It removes temporary bucket
directories and deletion tombstones, ignores non-directories, and removes
directories that have no manifest. For a published bucket it calls
`_load_bucket`, reconstructs versions named by the manifest, advances the
maximum sequence, and then calls `_clean_bucket`.

`_clean_bucket` calculates the set of storage IDs referenced by the recovered
bucket. It removes temporary files and every artifact whose stem is not
referenced, then removes empty object directories. Therefore a crash before
manifest publication leaves harmless new orphan artifacts: restart trusts the
old manifest and deletes the orphans. A crash after publication keeps the new
artifacts because the new manifest references them; old unreferenced artifacts
are reclaimed.

Recovery does not attempt to guess intent from leftover files. This is a
powerful design principle: make one small committed record authoritative, then
treat everything else as reconstructible or garbage.

Bucket creation and deletion use related directory protocols.
`DiskStorage.create_bucket` builds a fully initialized temporary bucket
directory, fsyncs its manifest and directory, renames it to its final name, and
fsyncs the buckets root. `delete_bucket` renames an empty bucket to a
`.deleted-` tombstone, fsyncs, removes it, and fsyncs again. Startup can finish
cleaning either temporary form.

## 6. Fault matrix

The essential outcomes are:

| Crash point | Published manifest | Restart-visible value | Recovery work |
|---|---|---|---|
| while writing a temporary artifact | old | old | remove temporary file |
| after artifacts, before manifest rename | old | old | remove unreferenced artifacts |
| after manifest rename, before cleanup | new | new | remove formerly referenced old artifacts |
| after cleanup | new | new | little or none |

The matrix says nothing about a caller receiving a success response, because
MiniS3 has no network protocol. It describes recovered storage state after
process death.

## 7. Hands-on experiment: crash on both sides

Run:

```bash
uv run python labs/lab_crash_atomicity.py
```

Measured output:

```text
Injected crash at 'before_manifest_publish'
After pre-publish crash: old
Injected crash at 'after_manifest_publish'
After post-publish crash: new
Observed states are complete 'old' or complete 'new', never partial.
```

The first attempted update writes new artifacts, crashes before the manifest
switch, and reopens to `old`. The second crashes after the switch and reopens
to `new`. `tests/test_storage.py` strengthens this lab with assertions about
orphan cleanup, temporary cleanup, directory-fsync chains, and multipart
completion on both sides of the same publication point.

This experiment uses direct file operations and a temporary local directory;
it does not require sockets or an external service.

## 8. Compared with Amazon S3

The mapping row for
[manifest rename](../mapping.md) is an **intentional simplification**. It
teaches atomic metadata visibility and a complete local fsync chain. Amazon S3
does not implement its global service as one POSIX directory and one JSON
manifest. Its durability and availability come from distributed storage,
replication or coding, failure detection, repair, and multi-node metadata
protocols that MiniS3 does not model.

MiniS3's promise is conditional on a local filesystem honoring the expected
same-filesystem atomic rename and fsync semantics. It does not cover disk
failure, controller caches that ignore flushes, bit rot, filesystem bugs,
multi-process writers, replicated durability, quorum behavior, online
scrubbing, or damaged-manifest repair. A valid published manifest is trusted.
These limits are explicit in the durability, recovery, and concurrency entries
of [Differences from Amazon S3](../DIFFERENCES.md).

The correct claim is therefore “a local crash-consistency protocol with
old-or-new visibility under stated POSIX assumptions,” not “eleven nines of
durability” and not “the architecture of S3.”

## Exercises

### Understanding

1. Why must the new artifacts be durable before the manifest is replaced?
2. Why is `fsync` on the temporary file insufficient after `os.replace`?
3. Why does recovery trust the manifest instead of selecting the newest
   artifact filename?

??? note "Reference answers"

    1. After publication, every manifest reference must resolve to a complete
       durable artifact. Publishing first could make new state point at missing
       or partial bytes after a crash.
    2. Rename changes a directory entry. The file's bytes may be durable while
       the new name is not; fsyncing the parent directory persists the naming
       change.
    3. Artifact presence does not encode transaction intent. The manifest is
       the single commit record; choosing by filename could expose a write that
       crashed before commit.

### Hands-on

4. Without changing `src/`, copy the lab's pattern into an inline script and
   add a crash at `before_manifest_publish`. After reopening, assert that no
   unreferenced `e*.data` or `e*.json` file remains for the failed update.

   **Acceptance:** GET returns the old body, an artifact listing contains only
   the manifest-referenced old storage ID, and `uv run pytest -q` stays green.

??? note "Reference answer"

    After reopening, inspect the one bucket manifest with `json.loads`, collect
    its referenced storage IDs, and compare them with artifact filename stems:

    ```python
    manifest_path = next((Path(root) / "buckets").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    referenced = {
        storage_id
        for ids in manifest["records"].values()
        for storage_id in ids
    }
    artifacts = {
        path.stem
        for path in (Path(root) / "buckets").rglob("e*.*")
    }
    assert artifacts == referenced
    ```

    Import `json` and `Path`. Use this only in the experiment; do not make
    production code depend on manifest internals.

5. Propose a fault-injection test diff for
   `after_object_directory_create`, without applying it.

   **Acceptance:** the proposal reopens the store after `InjectedCrash`, checks
   that the old object view remains valid, and explains that the hook tests the
   directory-fsync chain rather than manifest atomicity alone.

??? note "Reference answer"

    The test should construct a `CrashOnce("after_object_directory_create")`,
    attempt a PUT for a key whose hashed directory does not exist, expect
    `InjectedCrash`, and reopen. The new key must be absent and preexisting
    keys must remain readable. This crash happens before the newly created
    object directory's parent is fsynced and before manifest publication, so
    it probes durable directory creation as a separate prerequisite.

## Summary

MiniS3 separates durable artifacts from visible reachability. Atomic writes
flush a temporary file, rename it, and flush the parent; new directory chains
are persisted as well. `persist_bucket` writes immutable artifacts first and
publishes one authoritative manifest last. Recovery trusts that manifest and
cleans everything else, producing old or new complete state around the commit
point. Chapter 6 reuses this same publication boundary for multipart upload,
where private staged parts become one visible object only at completion.
