# 06 — Multipart Upload

## Learning objectives

By the end of this chapter, you can:

- explain why uploaded parts remain invisible until completion;
- state when the minimum part-size rule can actually be checked;
- derive a multipart ETag from the binary MD5 digests of its parts;
- trace completion from staged files to one atomically visible object; and
- distinguish MiniS3's faithful state-machine invariants from its local, in-memory assembly.

## Mechanism: private pieces, one public object

A large object is awkward to upload as one request. Multipart upload separates the work into four operations: initiate an upload, upload numbered parts, complete it with an ordered manifest, or abort it. The important abstraction is not merely “split a byte string.” It is a publication protocol. Parts are private intermediate state; only a successful completion creates an object.

`src/minis3/multipart.py` defines that state. `MultipartUpload` binds an `upload_id` to a bucket and exact key. `MultipartPart` is the receipt returned to the caller, while `StagedPart` represents bytes recovered from private storage. These types deliberately keep a staged part separate from `src/minis3/model.py::Version`, the public immutable object value.

Initiation happens in `src/minis3/store.py::MiniS3.create_multipart_upload`. Under the store lock it verifies the bucket, allocates a deterministic ID such as `u00000001`, and calls `src/minis3/storage/disk.py::DiskStorage.create_multipart_upload`. The storage method creates:

```text
buckets/<bucket>/uploads/<upload-id>/
  upload.json
  parts/
```

No bucket `ObjectRecord` is changed. `MiniS3.list_objects` reads bucket records, not `uploads/`, so an unfinished upload cannot leak into GET or LIST. This is a semantic boundary, not a UI convention.

`src/minis3/store.py::MiniS3.upload_part` accepts part numbers 1 through 10,000. It constructs a `StagedPart`, then delegates to `DiskStorage.write_multipart_part`. That method first calls `DiskStorage.load_multipart_upload`, which verifies that bucket, key, and upload ID agree with `upload.json`. It then publishes the part with `src/minis3/storage/atomic.py::atomic_write`. Re-uploading the same number replaces the staged file atomically. It does not append another public version.

Why does upload accept a tiny part even though S3 normally requires 5 MiB? At upload time, the service cannot know whether that part will be last. The completion manifest chooses both membership and order. Therefore `src/minis3/multipart.py::validate_completion` enforces `minimum_part_size` only on `selected[:-1]`. MiniS3 defaults to `MIN_PART_SIZE = 5 * 1024 * 1024`; tests and labs inject a smaller positive value to demonstrate the rule without allocating large buffers.

Completion is deliberately skeptical of the client. `validate_completion` rejects an empty manifest, numbers that are not strictly increasing, missing parts, stale or forged ETags, and undersized non-final parts. A staged part not named by the manifest is not included. These checks make the completion list a precise commit declaration rather than a suggestion.

The multipart ETag is the chapter's classic trap. `validate_completion` computes:

```python
digests = b"".join(
    md5(part.body, usedforsecurity=False).digest() for part in selected
)
composite = md5(digests, usedforsecurity=False).hexdigest()
```

It hashes the concatenation of the **binary** 16-byte MD5 digests, not the printable hexadecimal strings and not the completed body. The result is quoted and suffixed with `-N`. Consequently, equal final bytes can have different ETags when their part boundaries differ.

`src/minis3/store.py::MiniS3.complete_multipart_upload` holds the same `RLock` used by object mutations. It reloads staged parts, validates the manifest, joins selected bodies in order, then calls `src/minis3/bucket.py::Bucket.put` with the composite ETag and `multipart_upload_id`. The candidate bucket is persisted by `src/minis3/storage/disk.py::DiskStorage.persist_bucket`: immutable object artifacts are written first and `manifest.json` is atomically renamed last. That manifest publication is the visibility point. Only afterward is staging removed.

This ordering also covers a subtle recovery case. If a process dies after the object manifest becomes durable but before upload cleanup, `DiskStorage._recover_uploads` finds the published version's `multipart_upload_id` and removes the leftover staging directory at restart. If it dies before manifest publication, the old object state remains authoritative and the durable unfinished upload can be resumed.

Abort is smaller but follows the same boundary. `MiniS3.abort_multipart_upload` calls `DiskStorage.remove_multipart_upload`, which renames staging to a tombstone, fsyncs the uploads directory, removes the tombstone, and fsyncs again. It never touches an already visible object.

### Follow the failure paths

The validation order makes failures safe to reason about. `complete_multipart_upload` reloads and validates everything before it creates the candidate `Bucket`. An `InvalidPartOrder`, `InvalidPart`, or `EntityTooSmall` therefore leaves both public object state and private staging unchanged. The caller may upload a corrected replacement part or submit a corrected manifest against the same upload ID. This differs from a partially applied transaction that would require rollback.

Once validation succeeds, completion consumes sequence numbers for the public version and enters the ordinary persistence path. If persistence fails before manifest rename, recovery continues to trust the old manifest; newly written object artifacts are unreferenced and are cleaned. Staging is still present because removal has not started. If persistence crosses the rename, the object is committed even if the client never receives the return value. Startup recognizes the recorded `multipart_upload_id` and removes staging. Like many storage APIs, a lost response near a commit boundary can leave the caller uncertain even though recovered state is unambiguous.

Versioning does not create a separate multipart state machine. Completion calls the same `Bucket.put` as a single PUT. In an unversioned or suspended bucket it replaces the current `null` slot according to normal rules; in an enabled bucket it creates a new named version and retains history. The only multipart-specific metadata attached to the `Version` is its composite ETag and upload ID for recovery cleanup. This reuse is important: adding a new ingestion path should not quietly invent different version semantics.

Part receipts deserve similar care. The receipt's ETag describes the currently staged bytes for that number. Re-uploading part 1 changes its receipt. A completion request carrying the old receipt fails rather than silently selecting the new bytes. Thus the client manifest detects accidental replacement between upload and completion. The receipt is an integrity/correlation value in this model, not proof of authentication and not a global object identifier.

## Compared with Amazon S3

The state-machine invariants are intentionally recognizable: CreateMultipartUpload returns an upload ID; UploadPart numbers range from 1 to 10,000; a repeated part number replaces the prior part; CompleteMultipartUpload supplies ordered part numbers and ETags; every completed part except the last normally has a 5 MiB minimum; AbortMultipartUpload discards unfinished state. The multipart ETag formula modeled here matches the familiar MD5-based form.

The boundaries matter just as much. Real S3 supports enormous objects, parallel network transfer, list-uploads and list-parts APIs, upload-part copy, additional checksum algorithms, permissions, billing, lifecycle cleanup of abandoned uploads, encryption-dependent ETag behavior, and distributed durability. MiniS3 has none of those. It assembles all selected parts into memory and publishes to one POSIX filesystem.

The exact classification is recorded in the [multipart rows of the mapping](../mapping.md#why-multipart-etags-are-not-content-hashes). The [Multipart and ETag entries in DIFFERENCES](../DIFFERENCES.md#m2-simplifications-and-semantic-departures) explicitly reject the claim that every production ETag is an MD5 content hash or that local fsync equals S3 durability.

## Hands-on experiment

Run the repository lab:

```bash
uv run python labs/lab_multipart_etag.py
```

Measured output in this repository:

```text
same body: True
single PUT ETag: "e1d44c23b69953b35433ff067798318a"
multipart ETag: "05888a49b792dfb72298daafe3807667-2"
ETags differ: True
```

The bodies compare equal, so the different ETags cannot describe only the final byte string. The first ETag comes from `src/minis3/model.py::content_etag`. The second comes from `validate_completion`, where `b"same-"` and `b"bytes"` contribute two binary part digests. The lab sets `minimum_part_size=3`; it does not change the production-like default.

You can also pin the complete state machine:

```bash
uv run pytest -q tests/test_multipart.py
```

The test module verifies invisibility before completion, ordered atomic publication, part replacement, all manifest errors, restart survival, abort, identity checking, and part-number bounds.

## Exercises

1. **Understanding.** Why would enforcing the minimum size in `upload_part` reject a legal upload?

??? note "Reference answer"
    A part's status as “last” is defined only by the later completion manifest. A small part may legally be the final selected part. Checking in `upload_part` would reject it before the service has the necessary context; `validate_completion` correctly checks all selected parts except the last.

2. **Understanding.** A developer computes `md5(part1.etag.encode() + part2.etag.encode())`. Identify two errors.

??? note "Reference answer"
    The formula needs the raw 16-byte MD5 digests, not quoted hexadecimal ETag text. It must also append `-2` and quote the composite. The implementation in `validate_completion` calls `.digest()` on each part body, concatenates those bytes, then uses `.hexdigest()` only for the outer hash.

3. **Hands-on.** Without changing `src/`, copy the lab to `/tmp`, split `same-bytes` as `b"s"`, `b"ame-"`, and `b"bytes"`, set `minimum_part_size=1`, and predict the suffix and ETag equality before running it.

    Acceptance: the script prints `same body: True`, a multipart suffix of `-3`, and `ETags differ: True`.

??? note "Reference answer"
    Change the three `upload_part` calls to part numbers 1, 2, and 3, pass all three receipts in increasing order, and set the injected minimum to 1. The exact composite hexadecimal value changes because boundaries are inputs; the completed bytes remain `same-bytes`.

4. **Hands-on.** Write `/tmp/multipart-order.py` that uploads parts 1 and 2, then attempts completion with `[part2, part1]`.

    Acceptance: `uv run python /tmp/multipart-order.py` catches and prints `InvalidPartOrder`, while a subsequent GET still raises `NoSuchKey`.

??? note "Reference answer"
    Import `InvalidPartOrder` and `NoSuchKey`, use `TemporaryDirectory`, and catch each exception explicitly. The failed validation occurs before `Bucket.put` and manifest publication, so no public object exists. Do not edit `src/`.

## Summary

Multipart upload is a small transaction protocol: durable private parts become one public immutable value only after an ordered, validated manifest crosses the bucket-manifest publication point. That explains the last-part size exception, replacement semantics, recovery behavior, and composite ETag. The next chapter reuses ETags for a different purpose—not identifying an upload layout, but guarding reads and mutations with conditional requests.
