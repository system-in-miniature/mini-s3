> **Language**: English | [简体中文](README.zh-CN.md)

# MiniS3

[![CI](https://github.com/system-in-miniature/mini-s3/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-s3/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniS3 is the eighth **System-in-Miniature** teaching project: a small,
deterministic S3-style object store whose important mechanisms fit in one
repository. M2 covers flat object keys, versioning and delete markers,
S3-style listing, durable multipart completion and its composite ETag trap,
ETag preconditions for caching/CAS, and manually clocked lifecycle expiration.
Visible disk changes remain locally crash-consistent on filesystems that honor
the documented POSIX rename/fsync assumptions.

It is intentionally a direct Python API rather than an HTTP server. The runtime
uses only the Python standard library; pytest is the sole development
dependency.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
uv run pytest -q
uv run python labs/lab_versioning.py
uv run python labs/lab_directory_illusion.py
uv run python labs/lab_crash_atomicity.py
uv run python labs/lab_multipart_etag.py
uv run python labs/lab_conditional_cas.py
```

Minimal API use:

```python
from minis3 import MiniS3

store = MiniS3("./minis3-data")
store.create_bucket("notes")
stored = store.put_object("notes", "team/plan.txt", b"ship M2")
assert store.get_object("notes", "team/plan.txt").body == b"ship M2"
print(stored.version_id, stored.etag)
```

`team/plan.txt` is one opaque key. MiniS3 never creates `team/`; a
directory-looking result appears only when `list_objects(delimiter="/")`
groups matching strings.

## M2 behavior

- Unversioned PUT replaces the single public `null` version.
- Enabled PUT creates deterministic IDs such as `v00000001`.
- Enabled DELETE adds a marker and retains older bytes.
- Version-addressed GET and DELETE operate on one exact retained entry.
- Suspended PUT replaces the `null` slot while named history remains.
- Current-object and version listings are strongly consistent.
- Durable writes fsync newly created directory entries and immutable artifacts
  before one atomic manifest rename; startup recovery removes temporary and
  unreferenced files.
- Multipart staging survives restart but remains absent from object listing;
  completion validates ordered part receipts and atomically publishes one
  object with S3's `md5(binary part digests)-N` ETag.
- GET supports `If-None-Match` (304-shaped `NotModified`) and `If-Match`;
  PUT/DELETE evaluate `If-Match` under the mutation lock and fail with the
  412-shaped `PreconditionFailed` when the observed ETag is stale.
- Pure expiration rules run only in an explicit `lifecycle_tick` at injected
  time: current versioned data gains a marker, while eligible noncurrent data
  versions are physically removed.

## Repository tour

```text
src/minis3/
  model.py         immutable versions, markers, records, and ETags
  bucket.py        bucket versioning state machine
  listing.py       prefix, delimiter, pagination, and version projections
  store.py         public multi-bucket service API
  storage/         disk layout, atomic publication, and recovery
  multipart.py     completion validation and composite ETags
  conditional.py   pure If-Match and If-None-Match decisions
  lifecycle.py     pure expiration-rule evaluation
labs/              runnable mechanism demonstrations
tests/             behavior and crash-boundary contracts
docs/mapping.md    MiniS3 ↔ real S3 concept mapping
docs/DIFFERENCES.md explicit omissions and semantic differences
```

The exact equivalence boundary for each M2 mechanism is recorded in
[docs/mapping.md](docs/mapping.md); local and protocol simplifications remain
explicit in [docs/DIFFERENCES.md](docs/DIFFERENCES.md).

## Trademark Notice

MiniS3 is an independent educational project. It is not affiliated with, endorsed by, or sponsored by Amazon.com, Inc. or its affiliates. "Amazon S3" is a trademark of its respective owner.
