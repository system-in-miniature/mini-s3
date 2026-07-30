# Chapter 4: Listing and the Directory Illusion

Object keys are flat strings, yet object-store consoles routinely show folders.
The apparent contradiction disappears once listing is understood as a
projection. A request supplies a `prefix` and optionally a `delimiter`;
matching strings are either returned as objects or grouped into derived common
prefixes. Nothing in the stored object model changes. MiniS3 implements this
entire illusion in `src/minis3/listing.py`.

## Learning objectives

By the end of this chapter, you will be able to:

- compute `contents` and `common_prefixes` for a prefix/delimiter request;
- explain why common prefixes are query results rather than stored records;
- describe MiniS3's lexicographic ordering and `max_keys` accounting;
- explain continuation-token binding and its mutation-between-pages limit;
- distinguish current-object listing from complete version listing and state
  the project's strong-consistency boundary.

## 1. Listing is a projection over one snapshot

`MiniS3.list_objects` in `src/minis3/store.py` holds the store's `RLock` and
passes the selected bucket's `records` to `listing.list_objects`. The pure
function builds a result from that one in-memory state. Because PUT, DELETE,
versioning changes, and listing use the same lock, a list call does not
interleave with a mutation inside this process.

The return type `ListObjectsResult` contains:

- `contents`: current visible objects;
- `common_prefixes`: derived group names;
- `key_count`: the number of contents and prefixes in this page;
- `next_token`: an opaque continuation token or `None`.

Its `is_truncated` property is true exactly when `next_token` is present.
`ListedObject` exposes only current metadata: exact key, ETag, size, and
version ID. It does not copy the body into the list result.

Before grouping, `list_objects` applies current visibility. It skips a missing
history and skips a record whose newest entry is a `DeleteMarker`. Thus list
agrees with default GET: a marker-hidden key is not a current object.

## 2. Prefix filters strings

For each record, the function first checks:

```python
if not key.startswith(prefix) or not record.versions:
    continue
```

The prefix is a literal string predicate. `photos/` has no stored directory
meaning; it simply selects keys whose first characters match. An empty prefix
selects every current object.

Suppose the store contains:

```text
photos/2025/a.jpg
photos/2026/b.jpg
photos/readme.txt
```

With `prefix="photos/"` and no delimiter, all three exact keys are contents.
With `prefix="photos/2025/"`, only the first matches. No tree traversal is
performed.

## 3. Delimiter creates common prefixes

After removing the prefix from a matching key, `list_objects` searches the
remaining suffix for the delimiter:

```python
suffix = key[len(prefix):]
if delimiter is not None and delimiter in suffix:
    boundary = suffix.index(delimiter) + len(delimiter)
    prefixes.add(prefix + suffix[:boundary])
else:
    contents[key] = ListedObject(...)
```

Only the first delimiter after the requested prefix matters. With empty prefix
and delimiter `/`, every example key contributes the same derived
`photos/`. A set deduplicates it. With prefix `photos/` and delimiter `/`, the
year-shaped keys contribute `photos/2025/` and `photos/2026/`, while
`photos/readme.txt` has no remaining slash and is returned as content.

Changing the request can therefore make the same stored key appear directly,
appear under a common prefix, or not match at all. This is why creating a
zero-byte key ending in `/` is not required for grouping. Applications may
choose to create such “folder marker” objects, but they are ordinary objects,
not directories, and MiniS3 gives them no special status.

An empty-string delimiter is rejected because it cannot define a meaningful
first boundary. Any nonempty string is accepted by MiniS3, although `/` is the
conventional S3 delimiter.

## 4. Ordering, page size, and tokens

MiniS3 builds a combined list of `(name, kind)` pairs for contents and common
prefixes, then calls `combined.sort()`. The names are therefore
lexicographically ordered, and contents plus common prefixes share the
`max_keys` budget. `key_count` is the combined page length, not only the number
of objects.

Pagination uses an offset into that sorted combined projection.
`_encode_token` serializes the offset, prefix, and delimiter as compact JSON,
then URL-safe-base64 encodes it without padding. `_decode_token` restores
padding, parses the JSON, and verifies that prefix and delimiter match the
current request. A malformed token, negative/noninteger offset, or token from a
different query raises `InvalidContinuationToken`.

“Opaque” means callers should pass the token back rather than derive meaning
from its representation. It does not mean cryptographically secret or signed.
MiniS3's token is deliberately simple and local.

There is also no pinned snapshot across requests. Each page call observes a
strongly consistent current state, but a mutation between page one and page two
can reorder the combined sequence relative to the stored offset. An item can
move across the boundary. This is stated in
[Differences from Amazon S3](../DIFFERENCES.md), and it is why per-call
consistency must not be inflated into a multi-page snapshot guarantee.

The implementation also exposes the cost model of this teaching design.
`list_objects` scans every record, builds dictionaries and a set, combines the
projected names, and sorts them for each request. The work is roughly linear
in records plus sorting of matching results, not an indexed prefix lookup.
That simplicity makes ordering and grouping inspectable, but it is not a
production scaling claim. A distributed object store needs partition-aware
indexes and continuation state whose design cannot be inferred from this
in-memory projection.

One edge case follows directly from slicing: `max_keys=0` returns an empty page
and, when results exist, a continuation token at offset zero. The API rejects
negative values.

## 5. Current objects versus versions

`list_object_versions` is a separate function with a separate result type. It
sorts keys, then emits every data version and delete marker in newest-first
order. It flags the first history entry as latest. It accepts a prefix but has
no delimiter grouping or pagination.

The two APIs answer different questions:

- `list_objects`: “Which complete objects are visible now, possibly grouped
  for navigation?”
- `list_object_versions`: “Which historical entries, including markers, are
  retained?”

Combining them would either leak hidden history into normal navigation or
discard the information needed for version recovery.

## 6. Hands-on experiment: change only the projection

Run:

```bash
uv run python labs/lab_directory_illusion.py
```

Measured output:

```text
Stored exactly these flat keys: ['photos/2025/a.jpg', 'photos/2026/b.jpg', 'photos/readme.txt']
prefix='', delimiter=None
  contents: ['photos/2025/a.jpg', 'photos/2026/b.jpg', 'photos/readme.txt']
  common prefixes: []
prefix='', delimiter='/'
  contents: []
  common prefixes: ['photos/']
prefix='photos/', delimiter='/'
  contents: ['photos/readme.txt']
  common prefixes: ['photos/2025/', 'photos/2026/']
No directory record was created; only the list projection changed.
```

The lab performs three reads over unchanged state. That makes the causal claim
strong: only request parameters changed, so the directory-shaped output must
be derived. `tests/test_listing.py` additionally checks pagination, query-bound
tokens, marker hiding, and version flattening.

## 7. Consistency and the real S3 comparison

MiniS3's current and version listings are strongly consistent inside one
process because every public call shares the same lock and list computation
reads the current in-memory bucket. A completed mutation installs the new
candidate; a list before it sees old state and a list after it sees new state.

Modern Amazon S3 also provides strong read-after-write consistency for object
PUTs, DELETEs, and list operations. Historically, S3 list behavior was
eventually consistent; AWS announced strong consistency in December 2020.
Design explanations that still prescribe delay or reconciliation solely
because “S3 listing is eventually consistent” are therefore historically
dated for modern general-purpose S3, though application-level caches and other
systems can introduce their own staleness.

The prefix/delimiter grouping invariant is equivalent within this project and
is recorded in [the mapping matrix](../mapping.md). MiniS3's pagination is an
intentional simplification: the token is unsigned, local, and offset-based; it
does not model a distributed continuation mechanism. Version listing omits
S3's key marker, version-ID marker, pagination fields, owners, timestamp
formatting, and encoding options. See the listing and version-listing rows in
[Differences from Amazon S3](../DIFFERENCES.md).

## Exercises

### Understanding

1. Given keys `a/1`, `a/2/x`, and `b`, what are contents and common prefixes
   for `prefix="a/"`, `delimiter="/"`?
2. Why can two individually strongly consistent page requests still fail to
   represent one stable multi-page snapshot?

??? note "Reference answers"

    1. Contents is `["a/1"]`; common prefixes is `["a/2/"]`. The prefix is
       removed before searching for the next delimiter.
    2. The lock protects each call, not the interval between calls. A mutation
       can change lexicographic positions before the second call interprets
       the saved offset.

### Hands-on

3. Write an inline script that inserts `a.txt`, `dir/x`, and `z.txt`, requests
   pages with `delimiter="/"` and `max_keys=2`, then combines both pages.

   **Acceptance:** the combined names are exactly
   `{"a.txt", "dir/", "z.txt"}`, the first page has a non-`None` token, and the
   second has `next_token is None`.

??? note "Reference answer"

    ```python
    first = store.list_objects("b", delimiter="/", max_keys=2)
    second = store.list_objects(
        "b",
        delimiter="/",
        max_keys=2,
        continuation_token=first.next_token,
    )
    names = {
        *(x.key for x in first.contents),
        *first.common_prefixes,
        *(x.key for x in second.contents),
        *second.common_prefixes,
    }
    assert names == {"a.txt", "dir/", "z.txt"}
    assert first.next_token is not None
    assert second.next_token is None
    ```

4. Propose, but do not apply, a test for token query binding.

   **Acceptance:** it obtains a token using one prefix or delimiter, reuses it
   with a different query, expects `InvalidContinuationToken`, and leaves
   `src/` unchanged.

??? note "Reference answer"

    ```diff
    +store = _populated_store(tmp_path)
    +first = store.list_objects("b", max_keys=1)
    +assert first.next_token is not None
    +with pytest.raises(InvalidContinuationToken):
    +    store.list_objects(
    +        "b", prefix="different", continuation_token=first.next_token
    +    )
    ```

    The no-prefix first request has multiple results, so `max_keys=1`
    necessarily produces a real token. Reusing that token with a nonempty
    prefix therefore reaches query-binding validation rather than passing
    `None`.

    `tests/test_listing.py::test_malformed_or_query_mismatched_tokens_are_rejected`
    already provides this contract.

## Summary

Listing does not discover directories; it computes a deterministic projection
from current flat keys. Prefix filters, delimiter groups, and pagination slices
one lexicographically ordered combination of objects and common prefixes.
Each call is strongly consistent inside MiniS3, while continuation tokens do
not pin state across calls. Chapter 5 follows a mutation below this read
projection and identifies the filesystem event that makes new state visible
after a crash.
