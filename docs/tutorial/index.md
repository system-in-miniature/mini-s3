# MiniS3: An Object Store in Nine Chapters

This book develops MiniS3 from one direct API call into a compact study of
object-storage semantics and local durability. Read the chapters in order:
each chapter assumes the vocabulary and mechanisms established by the previous
one, and every mechanism claim points back to a concrete function under
`src/minis3/`.

MiniS3 is a teaching kernel, not an Amazon S3 replacement. Keep
[the mapping matrix](../mapping.md) and
[the explicit differences](../DIFFERENCES.md) beside the book: they separate
equivalent observable invariants from intentional simplifications and
unimplemented production concerns.

## How to use the book

1. Run commands from the repository root with `uv run`.
2. Read the named source function after the mechanism explanation, not before
   the chapter gives it a role.
3. Compare measured output with the output block in the experiment.
4. Attempt the exercises before opening the folded reference answers.
5. Keep exercise changes outside `src/` unless the exercise asks for a proposed
   diff; the tutorial itself never modifies the implementation.

## Chapters

1. **[Meet MiniS3](01-getting-started.md)** — Set up the environment, create a
   bucket and object, learn the direct API boundary, and map the rest of the
   book.
2. **[Objects, Flat Keys, and ETags](02-objects-etag.md)** — Separate opaque
   keys, immutable values, public version IDs, internal storage IDs, and
   single-PUT MD5 ETags.
3. **[Versioning, Delete Markers, and the Null Slot](03-versioning.md)** —
   Follow the irreversible versioning state machine, recover hidden history,
   and distinguish ordinary from version-addressed deletion.
4. **[Listing and the Directory Illusion](04-listing.md)** — Derive contents
   and common prefixes from flat strings, paginate the projection, and define
   the strong-consistency boundary.
5. **[Crash Atomicity and Manifest Publication](05-crash-atomicity.md)** —
   Trace immutable artifacts, file and directory fsync, atomic manifest
   replacement, crash injection, and startup cleanup.
6. **[Multipart Upload](06-multipart.md)** — Stage private parts, validate the
   completion manifest, publish atomically, and derive the multipart ETag.
7. **[Conditional Requests and CAS](07-conditional.md)** — Turn
   `If-Match`/`If-None-Match` into cache validation and serialized
   compare-and-swap behavior.
8. **[Lifecycle Expiration](08-lifecycle.md)** — Evaluate pure current and
   noncurrent expiration rules using an injected clock and explicit tick.
9. **[Methodology and Boundaries](09-methodology.md)** — Connect the
   experiments to the System-in-Miniature method and identify the distributed,
   security, and operational mechanisms beyond this repository.

## Reference shelf

Use the [quick start](../index.md) for the shortest runnable path, the
[mechanism mapping](../mapping.md) for equivalence classifications, the
[labs guide](../labs-guide.md) for experiment-oriented navigation, and
[Differences from Amazon S3](../DIFFERENCES.md) whenever a production
comparison matters.
