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

## M2 simplifications and semantic departures

- **ETag:** single PUT uses quoted whole-body MD5; multipart complete faithfully
  uses `md5(concatenated binary part MD5 digests)-N`. Real S3 ETags are still
  not universally MD5-derived because encryption and other service choices
  can change their meaning.
- **Version IDs:** real S3 IDs are service-generated opaque strings. MiniS3
  deliberately uses injected monotonic values (`v00000001`, …) so tests,
  recovery, and labs are reproducible.
- **Time:** versions store a numeric creation time. Tests and lifecycle labs
  inject a clock; a normal store defaults to the process wall clock. MiniS3
  does not model full S3 Last-Modified response formatting.
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
- **Version listing:** MiniS3 returns all matching versions and delete markers in
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
- **Multipart:** upload staging is durable and private, but there is no list
  uploads/parts API, upload expiration, parallel streaming assembler, alternate
  checksum family, copy-part, or 5 TiB scale model. Complete joins parts in
  memory before the ordinary local atomic-write/manifest publication path.
- **Conditions:** the direct API accepts exact quoted ETags, comma-separated
  alternatives, and `*`; it does not parse weak validators or reproduce the
  complete HTTP header precedence matrix. `NotModified` and
  `PreconditionFailed` stand in for 304 and 412 responses.
- **Lifecycle:** rules are passed to each explicit tick rather than stored as
  bucket configuration. Age is measured from version creation time, including
  for noncurrent versions; real S3's noncurrent-day semantics begin when a
  version becomes noncurrent. Unversioned current expiration physically
  removes the null object; versioned current expiration creates a marker.
