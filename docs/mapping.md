> **Language**: English | [简体中文](zh/mapping.md)

# MiniS3 ↔ Amazon S3 mapping

The labels distinguish a faithful teaching mechanism from a simplified
surface and from planned or excluded behavior:

- **A — aligned:** the core observable mechanism matches modern S3.
- **S — simplified:** the teaching mechanism is present, but the production
  surface, scale, or edge cases are reduced.
- **N — not implemented:** deliberately outside M1 or outside the project.

| MiniS3 concept | Real S3 concept | Level | Mapping |
|---|---|---:|---|
| Bucket | General purpose bucket | S | Named ownership boundary; no region, account, endpoint, or naming-rule model. |
| Flat string key | Object key | A | `/` is an ordinary character; neither system stores directories. |
| Whole-body PUT | PutObject | A | Replaces the complete current value rather than editing byte ranges in place. |
| Quoted content MD5 | Single-part ETag | S | Matches the familiar unencrypted single-part form only. |
| `null` version | Pre-versioning/suspended null version | A | One replaceable null slot coexists with named history after suspension. |
| Enabled version IDs | S3-generated version IDs | S | State transitions align; IDs are readable injected-counter values for determinism. |
| Delete marker | Delete marker | A | A marker becomes latest and hides older bytes without destroying them. |
| Version-addressed GET/DELETE | `versionId` query | A | Addresses one exact retained data version or marker. |
| `prefix` + `delimiter` | ListObjectsV2 grouping | A | `CommonPrefixes` is derived from key strings and request parameters. |
| Continuation token | ListObjectsV2 continuation token | S | Opaque and query-bound, but local and unsigned; no distributed snapshot lease. |
| Version listing | ListObjectVersions | S | Flattens all entries with `is_latest`; M1 omits markers/pagination fields from the wire API. |
| Manifest rename | Internal metadata commit | S | Teaches atomic visibility, not S3's distributed metadata architecture. |
| Startup recovery | Service recovery | S | Removes local tmp/orphan files; no replication or multi-node repair. |
| Multipart/conditions/lifecycle | Corresponding S3 APIs | N | M2 boundaries exist as docstrings, with no callable M1 behavior. |

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
