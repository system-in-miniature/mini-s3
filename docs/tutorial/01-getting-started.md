# Chapter 1: Meet MiniS3

MiniS3 is not a small clone of every Amazon S3 feature. It is a small,
deterministic object store that makes a carefully selected set of mechanisms
readable: flat keys, immutable object values, version histories, list
projections, crash-atomic publication, multipart completion, conditional
writes, and lifecycle expiration. This chapter gets the project running and
then uses one bucket and one object to establish the boundaries that the rest
of the book will deepen.

## Learning objectives

By the end of this chapter, you will be able to:

- create a temporary MiniS3 store, bucket, and object through the direct Python
  API;
- trace the first write through `MiniS3.put_object` and explain what the
  returned `Version` represents;
- distinguish a bucket, an object key, an object value, a version ID, and an
  ETag;
- locate the durable root and explain why the tutorial uses temporary
  directories for disposable experiments;
- state what MiniS3 deliberately does **not** prove about the Amazon S3 service.

## 1. Why read a system in miniature?

Production object storage combines a public protocol, authentication,
multi-tenant control planes, distributed metadata, replication, placement,
repair, billing, and enormous operational scale. Those concerns matter, but
they can obscure the smaller semantic questions a new reader first needs to
answer. Is a slash in a key a directory separator? What exactly becomes
visible after a successful PUT? What does DELETE mean after versioning is
enabled? Where is the atomic commit point?

MiniS3 keeps these questions and removes unrelated scale. The repository's
public boundary is `src/minis3/store.py`, class `MiniS3`. Its module docstring
is explicit: this is an SDK-shaped service facade, not an HTTP server.
`MiniS3.__init__` accepts a filesystem root, constructs `DiskStorage`, reloads
published buckets through `DiskStorage.load_buckets`, and creates one
`threading.RLock` for serialized in-process calls. This is already a useful
systems lesson: a narrow API does not mean “only memory.” The facade coordinates
an in-memory view with a durable representation.

The constructor also exposes three teaching seams:

```python
def __init__(
    self,
    root,
    *,
    counter=None,
    crash_injector=None,
    clock=None,
    minimum_part_size=MIN_PART_SIZE,
):
```

The `counter` makes IDs deterministic, `crash_injector` turns filesystem
boundaries into reproducible experiments, and `clock` makes time-based rules
testable. Real services cannot pause time or request a process crash at a named
line; a teaching kernel can, and that controllability is why its mechanisms are
easier to inspect.

## 2. Environment and repository map

MiniS3 requires Python 3.12 or later and uses
[uv](https://docs.astral.sh/uv/) for the project environment. From the
repository root:

```bash
uv sync --dev
uv run pytest -q
```

The runtime has no third-party dependencies; pytest is a development
dependency. `uv run` matters because it selects the locked project environment
and installs the `src/minis3` package correctly. A system Python invocation may
not see that package.

The main reading paths are:

| Path | Responsibility |
|---|---|
| `src/minis3/store.py` | public multi-bucket API and mutation lock |
| `src/minis3/model.py` | immutable data versions, delete markers, and ETags |
| `src/minis3/bucket.py` | one bucket's records and versioning state machine |
| `src/minis3/listing.py` | current and historical list projections |
| `src/minis3/storage/` | filesystem layout, publication, and recovery |
| `labs/` | deterministic mechanism demonstrations |
| `tests/` | executable semantic and crash-boundary contracts |

Do not begin by reading every file from top to bottom. Start at a public call,
follow the owned state, and stop when you reach the durable boundary. The next
section does exactly that for PUT.

This call-oriented reading discipline also separates interface evidence from
implementation evidence. Seeing `put_object` in `__init__.py` proves that the
method is publicly reachable; it does not yet prove persistence, replacement,
or recovery semantics. Those claims require following the call into
`Bucket.put`, `DiskStorage.persist_bucket`, and the corresponding tests.
Conversely, finding a helper deep in `storage/` does not prove callers can
exercise it through the supported API. Each chapter therefore pairs a public
entry point with the internal function that owns the mechanism and an
experiment that makes its observable result concrete.

## 3. The first bucket and object

`MiniS3.create_bucket` in `src/minis3/store.py` enters the store lock, rejects a
duplicate name, creates a `Bucket`, asks `DiskStorage.create_bucket` to publish
it, and only then adds it to the in-memory bucket map. A bucket is therefore an
ownership and naming boundary, not a directory that contains user-visible
subdirectories.

`MiniS3.put_object` follows the same “candidate then publish” shape:

```python
with self._lock:
    candidate = deepcopy(self._bucket(bucket))
    result = candidate.put(key, body, self._counter, now=self._clock())
    self._storage.persist_bucket(candidate)
    self._buckets[bucket] = candidate
    return result
```

This short slice is the first important mechanism in the book. The live
`Bucket` is not mutated first. MiniS3 copies it, applies `Bucket.put`, persists
that candidate, then swaps the in-memory reference. If persistence raises, the
old in-memory bucket remains authoritative in the running process. Chapter 5
will show how the manifest gives the same old-or-new boundary after restart.

`Bucket.put` in `src/minis3/bucket.py` copies the supplied bytes, assigns a
public version ID and a unique internal storage ID, calculates an ETag, and
creates a frozen `Version` from `src/minis3/model.py`. In a new, unversioned
bucket, the public version ID is the literal string `"null"`. “Null” is a real
public slot name here, not Python's `None`.

`MiniS3.get_object` looks up the bucket under the same lock and delegates to
`Bucket.get`. Without a `version_id`, `Bucket.get` reads the newest entry. It
returns a `Version` for data or raises `NoSuchKey` if the key is absent or its
newest entry is a delete marker.

## 4. Hands-on experiment: one complete round trip

Run the following from the repository root. A temporary directory keeps the
experiment repeatable and leaves no local store behind.

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minis3 import MiniS3

with TemporaryDirectory() as root:
    store = MiniS3(root)
    store.create_bucket("notes")
    stored = store.put_object("notes", "team/plan.txt", b"ship MiniS3")
    loaded = store.get_object("notes", "team/plan.txt")
    print(stored.version_id)
    print(stored.etag)
    print(loaded.body.decode())
PY
```

Measured output:

```text
null
"174ea9a5b4991a70e5ca3cb0b9805697"
ship MiniS3
```

The first line confirms the unversioned `null` slot. The second is a quoted MD5
fingerprint of the complete body, produced by `content_etag` in
`src/minis3/model.py`; it is not an authentication tag. The third confirms that
GET returned the complete bytes. The key contains a slash, but this experiment
did not create a `team` directory in the object model. Chapter 2 will make that
distinction precise.

For a persistent experiment, replace `TemporaryDirectory` with a path such as
`"./minis3-data"`. Reopening `MiniS3("./minis3-data")` calls
`DiskStorage.load_buckets` and reconstructs the published state. Delete that
directory only when you intentionally want to reset the experiment.

## 5. Compared with Amazon S3

The closest real-service operations are `CreateBucket`, `PutObject`,
`GetObject`, and `HeadObject`. At the semantic level, both systems treat a PUT
as replacement of a complete object value rather than an in-place byte-range
edit. MiniS3's `head_object`, however, simply returns the same local `Version`
as GET, including the bytes. Amazon S3 HEAD is an HTTP response without the
object body.

The larger boundary is transport and deployment. MiniS3 has no HTTP/XML
endpoint, SigV4 request signing, IAM, regions, accounts, bucket policies,
encryption, storage classes, replication, quotas, or distributed durability.
Python exceptions stand in for HTTP-shaped outcomes. One process and one
`RLock` stand in for concurrency control. Local `fsync` and atomic rename stand
in for a narrow crash-consistency lesson, not the internals of Amazon S3.

These are not footnotes to hide. The repository records the bucket, flat-key,
whole-body PUT, ETag, and manifest correspondences in
[the mapping matrix](../mapping.md), and lists protocol and production
omissions in [Differences from Amazon S3](../DIFFERENCES.md). Throughout this
book, “S3-style” means a named invariant matches within that documented
boundary; it never means wire compatibility or production equivalence.

## 6. Book map

The remaining chapters build outward from today's round trip:

1. [Objects and ETags](02-objects-etag.md) separates keys, immutable values,
   public version IDs, storage IDs, and fingerprints.
2. [Versioning](03-versioning.md) adds the irreversible state machine, retained
   history, and delete markers.
3. [Listing and the directory illusion](04-listing.md) derives directory-like
   views from flat key strings and studies pagination.
4. [Crash atomicity](05-crash-atomicity.md) follows immutable artifacts,
   `fsync`, rename, manifests, and startup cleanup.
5. Chapters 6–8 add multipart upload, conditional CAS, and deterministic
   lifecycle expiration.
6. Chapter 9 closes with the methodology and the production features that
   remain beyond this miniature.

## Exercises

### Understanding

1. Why does `MiniS3.put_object` mutate a deep-copied bucket before replacing
   the live in-memory bucket?
2. In the measured output, what does `null` mean, and what does it **not** mean?

??? note "Reference answers"

    1. The copy lets persistence finish before the running process exposes the
       candidate state. If persistence fails, the existing in-memory bucket is
       unchanged. Chapter 5 adds the restart-side half of this reasoning.
    2. `null` is the public version ID used by an unversioned or suspended
       bucket's replaceable slot. It is not “no object,” Python `None`, or an
       absent durable artifact.

### Hands-on

3. Without changing `src/`, extend the inline experiment so it closes the first
   `MiniS3` instance, opens a second instance on the same temporary root, and
   verifies that `team/plan.txt` still contains `b"ship MiniS3"`.

   **Acceptance:** the script prints `recovered: True`, and
   `uv run pytest -q` remains green.

??? note "Reference answer"

    Add these lines inside the temporary-directory block:

    ```python
    reopened = MiniS3(root)
    print(
        "recovered:",
        reopened.get_object("notes", "team/plan.txt").body == b"ship MiniS3",
    )
    ```

    This is an experiment-only edit. Do not place it in `src/`.

## Summary

MiniS3's direct API is a deliberately narrow window onto real storage ideas:
one facade serializes calls, bucket logic builds immutable versions, and a
durable storage layer publishes candidate state before the process exposes it.
The first PUT returned a `null` version and a quoted ETag, but those two fields
encode very different identities. Chapter 2 separates those identities and
shows why an object key is flat even when it looks like a path.
