# Self-Guided Rebuild

Each Stage is a complete independent-browser lesson: understand the current problem, concepts, and necessity; connect related files and critical statements through mechanism blocks; then close with evidence and your own explanation.

This is the browser-based path among MiniS3's three learning modes. Use the [Mechanism Tutorial](../tutorial/index.md) for topic-oriented study, or the [Agent-Guided usage guide](../agent-guided.md) for interactive CLI teaching.

For an editor-focused diff, run `python journey/tools/build_journey.py study N` and open `../MiniS3-journey-workspace`.

| Stage | Topic | New tests | Book chapter |
|---:|---|---:|---:|
| [01](stage-01.md) | Scaffold and object values | 3 | [1](../tutorial/01-getting-started.md) |
| [02](stage-02.md) | Bucket state and deterministic IDs | 1 | [3](../tutorial/03-versioning.md) |
| [03](stage-03.md) | Durable storage boundary | 1 | [5](../tutorial/05-crash-atomicity.md) |
| [04](stage-04.md) | Object service facade | 15 | [2](../tutorial/02-objects-etag.md) |
| [05](stage-05.md) | Version history projection | 3 | [3](../tutorial/03-versioning.md) |
| [06](stage-06.md) | Listing and the directory illusion | 5 | [4](../tutorial/04-listing.md) |
| [07](stage-07.md) | Manifest publication crash matrix | 5 | [5](../tutorial/05-crash-atomicity.md) |
| [08](stage-08.md) | Directory fsync and startup cleanup | 3 | [5](../tutorial/05-crash-atomicity.md) |
| [09](stage-09.md) | Multipart domain and validation | 1 | [6](../tutorial/06-multipart.md) |
| [10](stage-10.md) | Durable multipart staging | 1 | [6](../tutorial/06-multipart.md) |
| [11](stage-11.md) | Atomic multipart completion | 4 | [6](../tutorial/06-multipart.md) |
| [12](stage-12.md) | Multipart crash recovery | 2 | [6](../tutorial/06-multipart.md) |
| [13](stage-13.md) | Conditional requests and CAS | 4 | [7](../tutorial/07-conditional.md) |
| [14](stage-14.md) | Deterministic lifecycle expiration | 4 | [8](../tutorial/08-lifecycle.md) |
| [15](stage-15.md) | Public API and parity closeout | 0 | [9](../tutorial/09-methodology.md) |
