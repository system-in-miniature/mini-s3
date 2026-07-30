# 09 — Methodology and Boundaries

## Learning objectives

By the end of this chapter, you can:

- read MiniS3 as a chain of explicit semantic and durability boundaries;
- classify a claim as equivalent, intentionally simplified, or not implemented;
- use tests, labs, mapping, and differences documentation as complementary evidence;
- explain which mechanisms must change for erasure coding, storage classes, and replication; and
- design a source-grounded extension without silently claiming Amazon S3 compatibility.

## Mechanism: a system in miniature, not a mock

MiniS3 is small because it selects mechanisms, not because correctness is optional. A mock might store `dict[(bucket, key)] = bytes` and return plausible values. MiniS3 instead preserves boundaries that make an object store worth studying: flat keys, immutable versions, bucket state transitions, projection-based listing, private multipart staging, conditional compare-and-swap, explicit lifecycle decisions, and crash-consistent publication.

The public boundary is `src/minis3/store.py::MiniS3`. Its methods look like a local SDK. They own call-level synchronization and coordinate domain state with storage. This is deliberately not an HTTP server. A future adapter could translate requests into these methods, but protocol parsing must not take ownership of versioning, ETag, or persistence semantics.

The domain boundary is split across focused modules. `src/minis3/model.py::Version`, `DeleteMarker`, and `ObjectRecord` define immutable history. `src/minis3/bucket.py::Bucket.put` and `Bucket.delete` own the versioning state machine. `src/minis3/listing.py::list_objects` derives prefix/delimiter views from flat keys. `src/minis3/multipart.py::validate_completion`, `src/minis3/conditional.py::etag_matches`, and `src/minis3/lifecycle.py::evaluate_expiration` isolate pure decisions from I/O.

The durability boundary lives in `src/minis3/storage/atomic.py::atomic_write` and `src/minis3/storage/disk.py::DiskStorage.persist_bucket`. Bytes and immutable metadata are fsynced before `manifest.json` is atomically renamed. That rename is the local visibility point. `DiskStorage.load_buckets` trusts published manifests and cleans temporary or orphaned artifacts. This gives a meaningful POSIX crash model without claiming disk redundancy or a distributed metadata service.

These boundaries provide a practical reading technique. For any operation, ask four questions:

1. What public method owns the transaction?
2. Which pure/domain function decides the state transition?
3. What persistent artifact represents the result?
4. What event makes the result visible?

For multipart completion, the answers are `MiniS3.complete_multipart_upload`, `validate_completion` plus `Bucket.put`, immutable version files referenced by the bucket manifest, and manifest rename. For conditional PUT, they are `MiniS3.put_object`, `require_if_match` plus `Bucket.put`, the same version artifacts, and the same rename. Shared answers reveal architectural reuse rather than duplicated feature code.

### Three different kinds of evidence

Source code explains how a mechanism is implemented, but source alone does not prove its observed contract. Tests and labs serve different roles.

The tests under `tests/` are executable specifications. `tests/test_versioning.py` pins irreversible enablement, null versions, and delete markers. `tests/test_listing.py` pins directory illusion and pagination. `tests/test_storage.py` injects crashes around publication. M2 tests cover multipart, conditions, and lifecycle. A green suite means those local contracts passed in the current environment; it does not certify behavior outside their scope.

Labs under `labs/` are narrative experiments. They print a small number of interpretable facts: retained versions, grouped prefixes, old-or-new crash outcomes, multipart ETag differences, or exactly one CAS winner. They are better for forming a mental model, while tests are better at guarding many edge cases.

Finally, [the mapping](../mapping.md) and [DIFFERENCES](../DIFFERENCES.md) constrain interpretation. The mapping separates semantic tier from availability. “Equivalent” means a named observable invariant aligns within the stated boundary, not that the service is interchangeable with S3. “Intentional simplification” means the concept exists with reduced protocol, scale, orchestration, or edge cases. “Not implemented” means there is no callable behavior. DIFFERENCES collects cross-cutting omissions and departures that a feature-by-feature table can hide.

This evidence model prevents two opposite mistakes. The first is overclaiming: “multipart ETags match, therefore MiniS3 is S3-compatible.” The second is dismissing: “it is local Python, therefore it teaches nothing real.” The accurate claim names the invariant and its boundary—for example, “MiniS3 implements the familiar binary-part-digest multipart ETag formula and atomic local publication, but not S3's distributed service, wire protocol, or universal ETag behavior.”

### Continuing beyond the current boundary

Erasure coding is not “split the file into multipart parts.” Multipart is an upload protocol whose result is still one logical object. Erasure coding is a storage layout: encode data into data and parity shards, distribute them across failure domains, verify checksums, reconstruct missing shards, and repair degraded placement. A sound extension would keep `Version` as the logical value while replacing or generalizing `DiskStorage` artifacts. It would need a shard manifest, placement policy, quorum or durability rules, fault injection, and reconstruction tests. Publication must still make one complete logical version visible.

Storage classes are not a string field alone. A production-like model needs class-specific placement and durability policy, transitions that copy or re-encode data safely, restoration state for archival tiers, billing/minimum-duration semantics if claimed, and reads that resolve the current physical location. Lifecycle currently returns only expiration actions. An extension could add a transition action, but acceptance must verify crash behavior during movement and ensure the manifest never points to incomplete data.

Replication is not copying the root directory after PUT. A replicated system must define an operation or state-transfer log, ordering, acknowledgements, retry idempotency, lag, fencing of stale leaders, conflict behavior, and a read-consistency contract. Conditional CAS currently relies on one `RLock`; across processes or regions it needs a metadata consensus/serialization mechanism or an explicitly weaker conflict model. Local `fsync` remains useful per node but cannot establish replicated durability.

An HTTP/S3 adapter is another independent layer. It requires request routing, XML serialization, status and header precedence, streaming bodies, authentication/signing if compatibility is claimed, and differential tests against a real service. The adapter should translate `NoSuchKey`, `NotModified`, and `PreconditionFailed`; it should not reimplement bucket transitions. Until that layer exists, socket or S3-client experiments are **需运行时验证** and cannot be presented as supported.

Security and operations widen the system further: IAM and bucket policies, encryption and key rotation, quotas, audit events, metrics, background scrub and repair, capacity management, upgrades, and multi-tenant isolation. Each needs its own ownership boundary and failure contracts. Adding names to a README is not implementation.

## Compared with Amazon S3

Amazon S3 is a managed, multi-tenant, regional service with distributed metadata and storage, replication and repair, authorization, encryption, checksums, multiple storage classes, lifecycle automation, event integrations, billing, observability, and an HTTP API with signed requests. Its implementation is not the local manifest architecture shown here.

MiniS3 aligns only with the explicitly mapped observable slices. Flat keys, whole-object replacement, delete-marker behavior, prefix/delimiter grouping, the modeled multipart ETag formula, and object-level conditional semantics are useful points of equivalence. Deterministic IDs, one-process locking, numeric clocks, local manifest publication, simplified listing tokens, manual lifecycle, and direct exceptions are teaching choices.

Read the [full behavior mapping](../mapping.md) before using an equivalence claim, then check [explicit non-goals and semantic departures](../DIFFERENCES.md). Those documents are part of the product contract, not apologies after the fact.

## Hands-on experiment

Run the complete executable contract:

```bash
uv run pytest -q
```

Measured output:

```text
.................................................                        [100%]
49 passed in 3.72s
```

This confirms all 49 repository tests passed in the measured environment. It covers direct Python behavior and the local POSIX-oriented crash model exercised by tests. It does **not** verify an HTTP endpoint, real Amazon S3, multiple processes, multiple machines, erasure coding, replication, IAM, encryption, or storage classes.

To connect behavior to ownership, list the defining functions:

```bash
rg -n '^    def (put_object|complete_multipart_upload|lifecycle_tick)|^def (list_objects|validate_completion|etag_matches|evaluate_expiration|atomic_write)' src/minis3
```

Inspect each hit with the four reading questions above. Line numbers may evolve; relative paths and function names are the stable tutorial anchors.

## Exercises

1. **Understanding.** Why is “Equivalent” in the mapping not the same as “drop-in compatible”?

??? note "Reference answer"
    The classification applies to one named observable invariant within a stated boundary. Drop-in compatibility would also require the wire protocol, authentication, complete error/header behavior, scale and concurrency semantics, and the rest of the API. Availability is tracked separately from semantic tier.

2. **Understanding.** Which boundary should own erasure coding: multipart validation, the bucket state machine, or storage? Why?

??? note "Reference answer"
    Storage should own shard encoding, placement, reconstruction, and repair because those change the physical representation of one logical immutable version. Multipart remains an upload protocol, while the bucket state machine retains logical version history. The service coordinates publication across the generalized storage boundary.

3. **Hands-on.** Create `/tmp/minis3-evidence.md` with one row each for multipart ETag, conditional CAS, HTTP compatibility, and replication. Give columns for source anchor, executable evidence, semantic tier, and availability.

    Acceptance: the first two rows cite concrete functions and tests/labs; HTTP and replication are marked not implemented with no invented passing experiment; every row links to `docs/mapping.md` or `docs/DIFFERENCES.md`.

??? note "Reference answer"
    Multipart can cite `multipart.py::validate_completion` and `tests/test_multipart.py`; CAS can cite `store.py::MiniS3.put_object` plus `tests/test_conditional.py`. HTTP compatibility and replication have no callable implementation, so record the explicit non-goals rather than a source anchor or fake pass.

4. **Hands-on.** Draft, without changing `src/`, a five-test acceptance list for a future storage-class transition.

    Acceptance: the list covers visible semantics, crash before publication, crash after publication, restart recovery/cleanup, and reads during or after transition; it names the proposed owner and visibility point.

??? note "Reference answer"
    A strong draft keeps `MiniS3` as coordinator, adds a storage transition operation and a lifecycle transition action, and retains manifest rename as the visibility point. Tests should prove old-or-new class visibility, never a missing/torn object, deterministic recovery, orphan cleanup, and byte-identical reads. Cost semantics must be excluded unless implemented.

## Summary

The durable lesson of MiniS3 is a method: preserve the real semantic boundary, isolate decisions from effects, define a visibility point, test failures around it, and state equivalence only at the granularity evidence supports. The repository ends before distributed S3 architecture begins, but it leaves a precise map for continuing. New features should extend these ownership and publication contracts—not replace them with names that merely resemble a production service.
