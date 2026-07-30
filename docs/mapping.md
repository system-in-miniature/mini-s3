> **Language**: English | [简体中文](zh/mapping.md)

# MiniS3 ↔ Amazon S3 mapping

The **Semantic tier** column uses the series-wide three-value vocabulary:

- **Equivalent:** the named observable invariant matches modern S3 within this
  project's stated boundary.
- **Intentional simplification:** the same idea is present, but production
  protocol, scale, orchestration, or edge cases are reduced.
- **Semantically opposite:** the implementation takes a path S3 deliberately
  does not; no current M2 row has this classification.

**Availability** is separate: **Available** means callable M2 behavior, while
**Not implemented** means only a planned boundary or explicit non-goal exists.

| MiniS3 concept | Real S3 concept | Semantic tier | Availability | Mapping |
|---|---|---|---|---|
| Bucket | General purpose bucket | Intentional simplification | Available | Named ownership boundary; no region, account, endpoint, or naming-rule model. |
| Flat string key | Object key | Equivalent | Available | `/` is an ordinary character; neither system stores directories. |
| Whole-body PUT | PutObject | Equivalent | Available | Replaces the complete current value rather than editing byte ranges in place. |
| Quoted content MD5 | Single-part ETag | Intentional simplification | Available | Matches the familiar unencrypted single-part form only. |
| `null` version | Pre-versioning/suspended null version | Equivalent | Available | One replaceable null slot coexists with named history after suspension. |
| Enabled version IDs | S3-generated version IDs | Intentional simplification | Available | State transitions align, including irreversible enablement; IDs are readable injected-counter values for determinism. |
| Delete marker | Delete marker | Equivalent | Available | A marker becomes latest and hides older bytes without destroying them. |
| Version-addressed GET/DELETE | `versionId` query | Equivalent | Available | Addresses one exact retained data version or marker. |
| `prefix` + `delimiter` | ListObjectsV2 grouping | Equivalent | Available | `CommonPrefixes` is derived from key strings and request parameters. |
| Continuation token | ListObjectsV2 continuation token | Intentional simplification | Available | Opaque and query-bound, but local and unsigned; no distributed snapshot lease. |
| Version listing | ListObjectVersions | Intentional simplification | Available | Flattens all entries with `is_latest`; MiniS3 omits markers/pagination fields from the wire API. |
| Manifest rename | Internal metadata commit | Intentional simplification | Available | Teaches atomic visibility and a complete local directory-fsync chain, not S3's distributed metadata architecture. |
| Startup recovery | Service recovery | Intentional simplification | Available | Removes local tmp/orphan files; no replication or multi-node repair. |
| Multipart state machine | CreateMultipartUpload / UploadPart / CompleteMultipartUpload / AbortMultipartUpload | Intentional simplification | Available | Durable private staging, ordered receipt validation, last-part size exception, abort, and atomic publication are present; local assembly is in memory and omits upload listing, checksums beyond MD5, and distributed orchestration. |
| Multipart ETag | Multipart object ETag | Equivalent | Available | Exactly quotes `md5(concatenated binary MD5 digest of each completed part)-N`; it is deliberately distinct from whole-body MD5. |
| GET ETag conditions | `If-Match` / `If-None-Match` | Equivalent | Available | Exact/current wildcard matches produce the 412/304-shaped outcomes; the direct API uses named exceptions instead of HTTP responses. |
| Conditional PUT/DELETE | S3 conditional writes | Equivalent | Available | ETag comparison and mutation share one serialized critical section, so stale writers fail with `PreconditionFailed`. |
| Expiration tick | Lifecycle current/noncurrent expiration | Intentional simplification | Available | Pure prefix/age rules are manually evaluated at injected time; current data in a versioned bucket creates a marker and noncurrent data is physically removed. No background scheduler or storage-class transition exists. |

## Why multipart ETags are not content hashes

A single PUT of `same-bytes` has the quoted MD5 of those complete bytes.
Uploading the same bytes as two parts instead hashes the two **binary** part
digests, then appends `-2`. Part boundaries are therefore part of the ETag
input: equal final bodies can legitimately have different ETags.

MiniS3 preserves that often-missed S3 behavior. It does not claim that every
real S3 ETag is MD5-derived; encryption and other service choices are outside
the equivalence boundary.

## Why conditional writes form a CAS

`If-Match` is useful only when “compare current ETag” and “publish replacement”
cannot interleave with another writer. MiniS3 evaluates both while holding the
store mutation lock. Two writers using the same observed ETag therefore have
one winner; after its publication changes the ETag, the other receives the
S3-shaped `PreconditionFailed` outcome.

## Why listing creates a directory illusion

Suppose the only stored keys are `photos/2025/a.jpg` and
`photos/2026/b.jpg`. Listing with no delimiter returns both keys. Listing with
`prefix="photos/"` and `delimiter="/"` instead returns the two strings
`photos/2025/` and `photos/2026/` as common prefixes. Nothing was created,
moved, or traversed: the server grouped matching flat strings at the first
delimiter after the prefix.

## List consistency changed in December 2020

Before **2020-12-01**, Amazon S3 documentation described eventual consistency
for some overwrite and list observations: a successful write could briefly be
missing from a subsequent list, or a list could expose an older view. That
history explains why older S3 designs often added consistency indexes.

On **2020-12-01**, AWS announced strong read-after-write consistency for S3
GET, PUT, and LIST operations (and related metadata-changing operations) in all
regions. Modern callers can expect a successful write to be immediately
reflected by subsequent lists.

MiniS3 aligns with the post-2020 model. Each call holds the store lock and
builds its result from the currently published manifest state. A mutation
becomes visible at manifest rename, so a list observes either the complete old
state or complete new state. Pagination tokens are positions, not frozen
multi-call snapshots; concurrent changes between pages can therefore change
later page membership, as documented in `DIFFERENCES.md`.
