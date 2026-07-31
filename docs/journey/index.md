# MiniS3 Journey

Start from an empty tree and complete each task card in order. Build first; peek at the patch only when stuck.

## Learn in VSCode

Use a dedicated learning repository so the VSCode gutter and Source Control
view show only one stage. The main checkout is never modified.

```bash
python journey/tools/build_journey.py study 3
code ../MiniS3-journey-workspace
```

To implement the stage yourself, prepare its clean previous-stage baseline and
then check your work:

```bash
python journey/tools/build_journey.py attempt 3
python journey/tools/build_journey.py check 3
```

`check` runs the stage's cumulative `tests.txt` subset and prints a
`git diff --stat` against a reference tree built directly from the patches.
`study` and `attempt` confirm before overwriting existing learning work; use
`--yes` to skip the prompt or `--workspace PATH` to choose another dedicated
repository.

| Stage | Topic | New tests | Book chapter |
|---:|---|---:|---:|
| [01](stage-01.md) | Scaffold and object values | 3 | [1](../tutorial/01-getting-started.md) |
| [02](stage-02.md) | Bucket state and deterministic IDs | 0 | [3](../tutorial/03-versioning.md) |
| [03](stage-03.md) | Durable storage boundary | 0 | [5](../tutorial/05-crash-atomicity.md) |
| [04](stage-04.md) | Object service facade | 15 | [2](../tutorial/02-objects-etag.md) |
| [05](stage-05.md) | Version history projection | 3 | [3](../tutorial/03-versioning.md) |
| [06](stage-06.md) | Listing and the directory illusion | 5 | [4](../tutorial/04-listing.md) |
| [07](stage-07.md) | Manifest publication crash matrix | 5 | [5](../tutorial/05-crash-atomicity.md) |
| [08](stage-08.md) | Directory fsync and startup cleanup | 3 | [5](../tutorial/05-crash-atomicity.md) |
| [09](stage-09.md) | Multipart domain and validation | 0 | [6](../tutorial/06-multipart.md) |
| [10](stage-10.md) | Durable multipart staging | 1 | [6](../tutorial/06-multipart.md) |
| [11](stage-11.md) | Atomic multipart completion | 4 | [6](../tutorial/06-multipart.md) |
| [12](stage-12.md) | Multipart crash recovery | 2 | [6](../tutorial/06-multipart.md) |
| [13](stage-13.md) | Conditional requests and CAS | 4 | [7](../tutorial/07-conditional.md) |
| [14](stage-14.md) | Deterministic lifecycle expiration | 4 | [8](../tutorial/08-lifecycle.md) |
| [15](stage-15.md) | Public API and parity closeout | 0 | [9](../tutorial/09-methodology.md) |


> `journey attempt` is an experimental placeholder; it will be redesigned as CS336-style test-driven assignments (shipped tests + interface stubs, implement until green, `check` as grader).
