# MiniS3 Tutorial

[中文版](zh/index.md)

MiniS3 is a deterministic Python teaching implementation of core S3-style
object-storage mechanisms: flat keys, quoted MD5 ETags, bucket versioning,
delete markers, prefix/delimiter listing, and crash-consistent local
publication. It exposes a direct Python API rather than an HTTP/S3-compatible
server.

## Install

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/system-in-miniature/MiniS3.git
cd MiniS3
uv sync --dev
```

## First experiment

```bash
uv run python labs/lab_versioning.py
```

The script writes two versions, creates a delete marker, shows that an ordinary
GET now raises `NoSuchKey`, and then retrieves the retained first version by
its version ID.

## Reading path

Use the repository tour for the code layout, then read the concept mapping.
Run all three labs before reading the differences chapter so that a successful
local experiment is not mistaken for Amazon S3 compatibility.

The [English README](https://github.com/system-in-miniature/MiniS3#readme)
contains the complete M1 scope and minimal API example. The
[design history archive](superpowers/README.md) reflects construction-time
plans; canonical docs and tests define current behavior.
