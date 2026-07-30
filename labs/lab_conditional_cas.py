"""Race two writers against one observed ETag compare-and-swap token."""

from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier

from minis3 import MiniS3, PreconditionFailed


with TemporaryDirectory() as root:
    store = MiniS3(root)
    store.create_bucket("demo")
    observed = store.put_object("demo", "counter", b"0").etag
    barrier = Barrier(2)

    def writer(body: bytes) -> str:
        barrier.wait()
        try:
            store.put_object("demo", "counter", body, if_match=observed)
        except PreconditionFailed:
            return "412 PreconditionFailed"
        return "stored"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(writer, (b"writer-a", b"writer-b")))

    # Scheduling chooses the winner, but the observable CAS invariant is stable.
    outcomes.sort(key=lambda outcome: outcome != "stored")
    final = store.get_object("demo", "counter")
    print(f"outcomes: {outcomes}")
    print(f"one winner: {outcomes.count('stored') == 1}")
    print(f"one 412: {outcomes.count('412 PreconditionFailed') == 1}")
    print(f"final body is complete: {final.body in {b'writer-a', b'writer-b'}}")
