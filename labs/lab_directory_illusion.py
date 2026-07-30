"""Show that directory views are list parameters, not stored directories."""

from tempfile import TemporaryDirectory

from minis3 import MiniS3


def show(store: MiniS3, *, prefix: str = "", delimiter: str | None = None) -> None:
    page = store.list_objects("demo", prefix=prefix, delimiter=delimiter)
    print(f"prefix={prefix!r}, delimiter={delimiter!r}")
    print("  contents:", [item.key for item in page.contents])
    print("  common prefixes:", list(page.common_prefixes))


def main() -> None:
    with TemporaryDirectory(prefix="minis3-listing-") as root:
        store = MiniS3(root)
        store.create_bucket("demo")
        keys = ("photos/2025/a.jpg", "photos/2026/b.jpg", "photos/readme.txt")
        for key in keys:
            store.put_object("demo", key, key.encode())

        print("Stored exactly these flat keys:", list(keys))
        show(store)
        show(store, delimiter="/")
        show(store, prefix="photos/", delimiter="/")
        print("No directory record was created; only the list projection changed.")


if __name__ == "__main__":
    main()

