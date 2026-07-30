"""Observe delete markers hiding—but not destroying—versioned data."""

from tempfile import TemporaryDirectory

from minis3 import MiniS3, NoSuchKey


def main() -> None:
    with TemporaryDirectory(prefix="minis3-versioning-") as root:
        store = MiniS3(root)
        store.create_bucket("demo")
        store.set_bucket_versioning("demo", "enabled")

        first = store.put_object("demo", "report.txt", b"draft one")
        second = store.put_object("demo", "report.txt", b"draft two")
        marker = store.delete_object("demo", "report.txt")

        print("PUT #1:", first.version_id, first.etag)
        print("PUT #2:", second.version_id, second.etag)
        print("DELETE created marker:", marker.version_id)
        try:
            store.get_object("demo", "report.txt")
        except NoSuchKey:
            print("GET without version-id: NoSuchKey (latest entry is a marker)")

        print("Retained history, newest first:")
        for item in store.list_object_versions("demo").versions:
            kind = "delete-marker" if item.is_delete_marker else "data"
            print(
                f"  {item.version_id}: {kind}, "
                f"is_latest={str(item.is_latest).lower()}"
            )

        recovered = store.get_object(
            "demo", "report.txt", version_id=first.version_id
        )
        print("GET the 'deleted' first version:", recovered.body.decode())


if __name__ == "__main__":
    main()

