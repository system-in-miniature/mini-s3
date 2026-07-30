# Chapter 2: Objects, Flat Keys, and ETags

An object store is easiest to misunderstand when familiar filesystem words are
silently imported into it. A key that reads `photos/2026/cat.jpg` looks like a
path, an ETag looks like a checksum, and a PUT looks like a file overwrite.
Each analogy is partly useful and partly dangerous. This chapter replaces the
analogies with MiniS3's concrete value model.

## Learning objectives

By the end of this chapter, you will be able to:

- explain why MiniS3's namespace is a map from opaque key strings to
  `ObjectRecord` histories;
- distinguish an object value, a `Version`, an `ObjectRecord`, a public
  `version_id`, and an internal `storage_id`;
- derive a single-PUT ETag using `content_etag` and state why it is not a
  universal content identity in real S3;
- explain whole-object replacement and immutability without confusing them
  with immutable Python variables;
- verify flat-key and replacement behavior through the direct API.

## 1. The value model

The authoritative definitions live in `src/minis3/model.py`. `ObjectRecord` is
a frozen dataclass with two fields: one exact `key` and a tuple of versions,
newest first. The key is not split, normalized, or interpreted:

```python
@dataclass(frozen=True, slots=True)
class ObjectRecord:
    key: str
    versions: tuple[ObjectVersion, ...] = ()
```

This means `/a//b/`, `a/b`, and `a//b` are three different keys. Leading,
trailing, and repeated slashes survive. There is no inode for `a`, no child
entry named `b`, and no directory traversal. `src/minis3/listing.py`,
function `list_objects`, can later group strings around a delimiter, but that
is a query projection rather than stored hierarchy.

`Version` represents one complete data value:

```python
@dataclass(frozen=True, slots=True)
class Version:
    version_id: str
    storage_id: str
    sequence: int
    body: bytes
    etag: str
    created_at: float = 0.0
    multipart_upload_id: str | None = None
```

The dataclass is frozen, so a caller cannot assign a new body or ETag to a
returned `Version`. More importantly, the storage design treats each version
as an immutable artifact. An update creates another `Version`; it does not
edit the old value in place. Whether the old version remains publicly retained
depends on the bucket's versioning state, which Chapter 3 covers.

`DeleteMarker` is the other member of the `ObjectVersion` union. It has
identity and creation time but no body or ETag. Its job is to become the newest
history entry and hide older data. Keeping data and markers as different types
makes invalid states harder to express: code cannot accidentally read
`marker.body`.

## 2. Public identity versus storage identity

`Bucket.put` in `src/minis3/bucket.py` obtains one sequence number, then derives
two identifiers from it. `version_id` is public object-history identity.
`storage_id` is always a unique string such as `e00000001` and names immutable
disk artifacts.

Why keep both? In an unversioned bucket, every visible PUT uses the public
version ID `"null"`. A suspended bucket also repeatedly replaces its public
`null` slot. Reusing `"null"` as a disk filename would require destructive
in-place replacement and would weaken the publication protocol. A fresh
`storage_id` lets MiniS3 write new artifacts first and switch the manifest only
after they are durable. Public semantics can say “replace the null slot” while
storage mechanics still say “never overwrite a published version artifact.”

The `sequence` is stored separately because ordering and recovery need a
numeric fact, while public and storage IDs are formatted strings. The default
`SequenceCounter` in `src/minis3/bucket.py` is deterministic. On startup,
`MiniS3.__init__` asks `DiskStorage.load_buckets` for the greatest recovered
sequence and advances the counter beyond it. Real S3 version IDs are opaque,
service-generated values; MiniS3's readable IDs are a testing simplification,
not a compatibility promise.

## 3. Whole-object replacement

`Bucket.put` begins with `body=bytes(body)`. That conversion captures a byte
value even if the caller supplied another bytes-like object. It then computes
the ETag and constructs a new frozen `Version`.

For an unversioned or suspended bucket, the function removes any existing
entry whose public ID is `"null"` and puts the new value first. In an enabled
bucket, it prepends the new value and retains every older entry. Both branches
replace the **current object value** as a whole. MiniS3 does not expose
byte-range mutation, append, or patch operations.

This is not the same as saying the Python `Bucket` aggregate is immutable.
`Bucket.records` is a mutable dictionary, and `Bucket.put` replaces its
`ObjectRecord` value. Immutability applies to the published value objects and
disk artifacts. The service safely coordinates aggregate mutation by copying a
bucket under `MiniS3.put_object`, persisting the candidate, and only then
installing it.

`MiniS3.get_object` returns the stored `Version` value. `head_object` calls
`get_object` and therefore returns that same value, including locally
available body bytes. This is convenient for a direct teaching API but differs
from HTTP HEAD.

## 4. What the ETag says

For an ordinary PUT, `Bucket.put` calls `content_etag` in
`src/minis3/model.py`:

```python
def content_etag(body: bytes) -> str:
    digest = md5(body, usedforsecurity=False).hexdigest()
    return f'"{digest}"'
```

Three details matter.

First, the input is the complete body. Equal bytes passed through this
single-PUT path receive equal ETags. Second, the hexadecimal digest is quoted
because S3 HTTP ETag values are quoted entity tags. Third,
`usedforsecurity=False` documents the role: MD5 is a familiar fingerprint in
this model, not a secure signature. An ETag does not authenticate the writer
or protect against a malicious collision.

The rule changes for multipart completion. There, MiniS3 hashes the
concatenation of the **binary MD5 digests of parts** and appends the part count.
Consequently the same final bytes can have different ETags depending on part
boundaries. Chapter 6 develops that mechanism. Even beyond multipart, real S3
ETags are not universally MD5 because encryption and service choices affect
their meaning. Code should treat an ETag as an opaque validator unless a
narrower contract is explicitly guaranteed.

## 5. Hands-on experiment: path-shaped keys and replacement

Run:

```bash
uv run python - <<'PY'
from dataclasses import FrozenInstanceError
from tempfile import TemporaryDirectory
from minis3 import MiniS3, content_etag

print(content_etag(b"hello"))
with TemporaryDirectory() as root:
    store = MiniS3(root)
    store.create_bucket("objects")
    first = store.put_object("objects", "/a//b/", b"hello")
    second = store.put_object("objects", "/a//b/", b"HELLO")
    print(first.version_id, second.version_id)
    print(store.get_object("objects", "/a//b/").body)
    print([item.key for item in store.list_objects("objects").contents])
    try:
        second.etag = "changed"
    except FrozenInstanceError:
        print("Version is frozen")
PY
```

Measured output:

```text
"5d41402abc4b2a76b9719d911017c592"
null null
b'HELLO'
['/a//b/']
Version is frozen
```

The list contains the exact path-shaped string, not a reconstructed path. Both
PUTs use the same public `null` slot because versioning has not been enabled,
and GET returns only the replacement body. The local variable `first` still
refers to the old frozen value, but it is no longer in the bucket's public
history. The freeze error confirms value-object immutability; the observed
replacement confirms aggregate mutation.

## 6. Compared with Amazon S3

Amazon S3 also uses a flat object-key namespace and PUT replaces the full
object value. The slash has conventional meaning to clients and consoles only
because listing requests use prefixes and delimiters. This invariant is marked
**Equivalent** in [the mapping matrix](../mapping.md).

MiniS3 narrows the model in several ways:

- bodies live in local files and are also loaded into `Version.body`; it does
  not stream multi-terabyte objects;
- single-PUT ETags are always quoted whole-body MD5, while real S3 ETags are
  not universally content MD5;
- IDs are deterministic and readable instead of opaque;
- `head_object` returns body bytes because there is no HTTP response layer;
- one local process owns metadata rather than a distributed service.

The precise ETag, HEAD, time, and concurrency departures are listed in
[Differences from Amazon S3](../DIFFERENCES.md). The productive comparison is
not “same implementation”; it is “same named object invariant under a much
smaller execution and durability boundary.”

## Exercises

### Understanding

1. Why is a unique `storage_id` necessary when multiple writes may all have
   public `version_id == "null"`?
2. Does a frozen `Version` make the entire store immutable? Explain the two
   levels separately.

??? note "Reference answers"

    1. The storage ID names a fresh immutable artifact for each write. The
       manifest can atomically switch from one artifact to another even though
       the public state machine calls both values `null`.
    2. No. A `Version` value cannot be modified, but `Bucket.records` is a
       mutable aggregate whose entries are replaced under the store lock.
       Updates create new immutable values and install new records.

### Hands-on

3. Without modifying `src/`, write an inline script that stores both `a/b` and
   `a//b`, then proves that two exact keys are listed and return different
   bodies.

   **Acceptance:** sorted listed keys equal `["a//b", "a/b"]`, both GET
   assertions pass, and `uv run pytest -q` stays green.

??? note "Reference answer"

    ```python
    with TemporaryDirectory() as root:
        store = MiniS3(root)
        store.create_bucket("b")
        store.put_object("b", "a/b", b"one")
        store.put_object("b", "a//b", b"two")
        keys = sorted(item.key for item in store.list_objects("b").contents)
        assert keys == ["a//b", "a/b"]
        assert store.get_object("b", "a/b").body == b"one"
        assert store.get_object("b", "a//b").body == b"two"
        print(keys)
    ```

4. Design—but do not apply—a patch that adds a `sha256` metadata field to
   `Version`. Identify every constructor, persistence, recovery, and test site
   that must change.

   **Acceptance:** your answer names at least `model.Version`, `Bucket.put`,
   `DiskStorage._write_artifact`, `DiskStorage._load_artifact`, and a model or
   storage test; no `src/` file is changed.

??? note "Reference answer"

    A correct patch plan adds the frozen field in `src/minis3/model.py`,
    computes it when `Bucket.put` constructs a version, serializes it from
    `DiskStorage._write_artifact`, validates/reconstructs it in
    `DiskStorage._load_artifact`, and updates direct `Version(...)`
    constructions and round-trip tests. It should also decide how older
    manifests without the field are handled. This is a design exercise only.

## Summary

MiniS3 stores an exact key string beside a newest-first tuple of immutable
values. Public version identity and internal storage identity are deliberately
separate, allowing the public `null` slot to be replaced without overwriting
published artifacts. A single-PUT ETag is a quoted MD5 fingerprint within this
teaching path, not a universal or secure identity. Chapter 3 now turns the
one-slot history into an explicit versioning state machine.
