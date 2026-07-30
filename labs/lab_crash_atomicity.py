"""Inject crashes on both sides of PUT's manifest publication point."""

from tempfile import TemporaryDirectory

from minis3 import InjectedCrash, MiniS3


class CrashOnce:
    """Deterministic one-shot crash hook for one named public boundary."""

    def __init__(self, target: str) -> None:
        self.target = target
        self.used = False

    def __call__(self, point: str) -> None:
        if point == self.target and not self.used:
            self.used = True
            raise InjectedCrash(point)


def attempt_put(root: str, crash_point: str, body: bytes) -> None:
    crashing = MiniS3(root, crash_injector=CrashOnce(crash_point))
    try:
        crashing.put_object("demo", "state.txt", body)
    except InjectedCrash:
        print(f"Injected crash at {crash_point!r}")


def main() -> None:
    with TemporaryDirectory(prefix="minis3-crash-") as root:
        store = MiniS3(root)
        store.create_bucket("demo")
        store.put_object("demo", "state.txt", b"old")

        attempt_put(root, "before_manifest_publish", b"never half-visible")
        after_pre_crash = MiniS3(root).get_object("demo", "state.txt")
        print("After pre-publish crash:", after_pre_crash.body.decode())

        attempt_put(root, "after_manifest_publish", b"new")
        after_post_crash = MiniS3(root).get_object("demo", "state.txt")
        print("After post-publish crash:", after_post_crash.body.decode())
        print("Observed states are complete 'old' or complete 'new', never partial.")


if __name__ == "__main__":
    main()

