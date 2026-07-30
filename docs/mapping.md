> **Language**: English | [简体中文](zh/mapping.md)

# MiniS3 ↔ Amazon S3 mapping

The **Semantic tier** column uses the series-wide three-value vocabulary:

- **Equivalent:** the named observable invariant matches modern S3 within this
  project's stated boundary.
- **Intentional simplification:** the same idea is present, but production
  protocol, scale, orchestration, or edge cases are reduced.
- **Semantically opposite:** the implementation takes a path S3 deliberately
  does not; no current M1 row has this classification.

**Availability** is separate: **Available** means callable M1 behavior, while
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
| Version listing | ListObjectVersions | Intentional simplification | Available | Flattens all entries with `is_latest`; M1 omits markers/pagination fields from the wire API. |
| Manifest rename | Internal metadata commit | Intentional simplification | Available | Teaches atomic visibility and a complete local directory-fsync chain, not S3's distributed metadata architecture. |
| Startup recovery | Service recovery | Intentional simplification | Available | Removes local tmp/orphan files; no replication or multi-node repair. |
| Multipart/conditions/lifecycle | Corresponding S3 APIs | Intentional simplification | Not implemented | M2 boundaries exist as docstrings, with no callable M1 behavior. |

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
