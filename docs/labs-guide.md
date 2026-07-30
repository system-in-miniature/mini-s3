# Chapter 4: Hands-on Experiments

[中文版](zh/labs-guide.md)

Run all commands from the repository root after `uv sync --dev`. The labs use
temporary directories and the public `MiniS3` API; they do not leave object
data in the repository.

## Versioning and delete markers

Source:
[lab_versioning.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_versioning.py)

```bash
uv run python labs/lab_versioning.py
```

Expected: PUTs create `v00000001` and `v00000002`; DELETE creates
`v00000003`. The marker becomes latest, ordinary GET reports `NoSuchKey`, and
version-addressed GET still returns `draft one`. Watch how deletion changes the
latest projection without destroying retained bytes.

## The directory illusion

Source:
[lab_directory_illusion.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_directory_illusion.py)

```bash
uv run python labs/lab_directory_illusion.py
```

Expected: three flat keys are stored. With no delimiter they are all contents;
with delimiter `/`, the root view reports only `photos/` as a common prefix;
under `photos/`, `photos/readme.txt` is content and the year paths are common
prefixes. Watch how listing parameters create a hierarchy without directory
records.

## Crash atomicity

Source:
[lab_crash_atomicity.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_crash_atomicity.py)

```bash
uv run python labs/lab_crash_atomicity.py
```

Expected: a crash before manifest publication reopens as complete `old`; a
crash after publication reopens as complete `new`. No partial body is visible.
Watch the manifest rename as the visibility boundary, and keep the documented
POSIX rename/fsync assumptions in mind.

## The multipart ETag mystery

Source:
[lab_multipart_etag.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_multipart_etag.py)

```bash
uv run python labs/lab_multipart_etag.py
```

Expected: two objects have exactly the same body. The single PUT has a plain
quoted MD5 ETag; the two-part upload has a different ETag ending in `-2`.
Watch the lab prove that multipart ETag input includes binary part digests and
part boundaries, not just the completed bytes.

## Conditional compare-and-swap

Source:
[lab_conditional_cas.py](https://github.com/system-in-miniature/mini-s3/blob/main/labs/lab_conditional_cas.py)

```bash
uv run python labs/lab_conditional_cas.py
```

Expected: two concurrent writers reuse one observed ETag. Exactly one stores a
replacement and exactly one receives `412 PreconditionFailed`; the final body
is one complete writer value. Watch the ETag check and mutation share one
critical section rather than becoming a check-then-write race.

Continue with the [Amazon S3 mapping](mapping.md) and
[declared differences](DIFFERENCES.md).
