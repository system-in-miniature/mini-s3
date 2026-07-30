> **Language**: English | [简体中文](zh/DIFFERENCES.md)

# Differences from Amazon S3

This file is the honesty boundary: MiniS3 teaches selected mechanisms and is
not a wire-compatible, secure, or distributed S3 replacement.

## Explicit non-goals

- IAM, bucket policies, ACLs, accounts, tenancy, and authorization
- server-side or client-side encryption and key management
- storage classes, archival restore, and storage-class migration
- replication across buckets, regions, or machines
- erasure coding (a possible M3 teaching extension)
- presigned URLs
- the S3 XML/HTTP wire protocol, DNS endpoints, and request signing
- event notifications
- quotas, billing, regional placement, and production bucket-name validation

## M1 simplifications and semantic departures

- **ETag:** every data version uses quoted hexadecimal content MD5. Real S3
  ETags are not universally content MD5: multipart uploads use
  `md5(concatenated binary part MD5 digests)-N`, and encryption or other
  implementation choices can further break the MD5 assumption. Multipart ETag
  behavior belongs to M2.
- **Version IDs:** real S3 IDs are service-generated opaque strings. MiniS3
  deliberately uses injected monotonic values (`v00000001`, …) so tests,
  recovery, and labs are reproducible.
- **Time:** M1 stores no Last-Modified timestamps and calls no wall clock.
  Lifecycle in M2 will add an injected clock and manual ticks.
- **HEAD:** `head_object` returns the same immutable `Version` value as GET,
  including locally available bytes. There is no transport, so MiniS3 does not
  model a body-less HTTP HEAD response.
- **Errors:** Python exception classes represent S3-shaped outcomes. There are
  no HTTP status lines, XML error documents, request IDs, or delete-marker
  response headers.
- **Listing:** keys and common prefixes are lexicographically ordered and
  counted together for `max_keys`. The token is opaque and bound to prefix and
  delimiter, but it is not signed and does not pin a distributed snapshot.
  Mutation between page requests may move page boundaries.
- **Version listing:** M1 returns all matching versions and delete markers in
  one simplified result. It omits S3's key/version markers, pagination,
  ownership, timestamps, and encoding options.
- **Concurrency:** one process serializes calls with a lock. There is no
  multi-process lock, distributed transaction, quorum, or conflict protocol.
- **Durability:** fsync + atomic rename provides a local-filesystem crash
  boundary. It does not promise replicated durability, disk fault tolerance,
  bit-rot repair, or behavior on filesystems that violate POSIX rename/fsync
  expectations.
- **Recovery:** a published manifest is authoritative. Startup deletes
  temporary directories/files and artifacts unreferenced by that manifest;
  there is no online scrubber or damaged-manifest repair.
- **Bucket surface:** buckets have no regions, ownership controls, object lock,
  tags, website configuration, CORS, logging, or production naming rules.

## Planned M2, not available now

- Multipart initiate/upload-part/complete/abort and multipart ETags
- If-Match / If-None-Match for GET caching and conditional PUT
- Deterministic current/non-current expiration through a manual lifecycle tick

The corresponding source modules contain only explanatory docstrings so their
future ownership is visible without suggesting that the behavior works.
