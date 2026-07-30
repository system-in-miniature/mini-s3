> **Language**: English | [简体中文](README.zh-CN.md)

# MiniS3

MiniS3 is the eighth **System-in-Miniature** teaching project: a small,
deterministic S3-style object store whose important mechanisms fit in one
repository. M1 focuses on flat object keys, quoted MD5 ETags, bucket
versioning, delete markers, S3-style listing, and crash-safe disk publication.

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
```

Minimal API use:

```python
from minis3 import MiniS3

store = MiniS3("./minis3-data")
store.create_bucket("notes")
stored = store.put_object("notes", "team/plan.txt", b"ship M1")
assert store.get_object("notes", "team/plan.txt").body == b"ship M1"
print(stored.version_id, stored.etag)
```

`team/plan.txt` is one opaque key. MiniS3 never creates `team/`; a
directory-looking result appears only when `list_objects(delimiter="/")`
groups matching strings.

## M1 behavior

- Unversioned PUT replaces the single public `null` version.
- Enabled PUT creates deterministic IDs such as `v00000001`.
- Enabled DELETE adds a marker and retains older bytes.
- Version-addressed GET and DELETE operate on one exact retained entry.
- Suspended PUT replaces the `null` slot while named history remains.
- Current-object and version listings are strongly consistent.
- Durable writes publish immutable artifacts through one atomic manifest
  rename; startup recovery removes temporary and unreferenced files.

## Repository tour

```text
src/minis3/
  model.py         immutable versions, markers, records, and ETags
  bucket.py        bucket versioning state machine
  listing.py       prefix, delimiter, pagination, and version projections
  store.py         public multi-bucket service API
  storage/         disk layout, atomic publication, and recovery
  multipart.py     M2 boundary (documentation only)
  conditional.py   M2 boundary (documentation only)
  lifecycle.py     M2 boundary (documentation only)
labs/              runnable mechanism demonstrations
tests/             behavior and crash-boundary contracts
docs/mapping.md    MiniS3 ↔ real S3 concept mapping
docs/DIFFERENCES.md explicit omissions and semantic differences
```

The planned M2 work—multipart upload, conditional requests, and lifecycle—is
not partially implemented. See [docs/DIFFERENCES.md](docs/DIFFERENCES.md).
