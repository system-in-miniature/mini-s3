"""Show why equal bytes do not imply equal S3 ETags."""

from tempfile import TemporaryDirectory

from minis3 import MiniS3


with TemporaryDirectory() as root:
    store = MiniS3(root, minimum_part_size=3)
    store.create_bucket("demo")
    single = store.put_object("demo", "single", b"same-bytes")

    upload = store.create_multipart_upload("demo", "multipart")
    first = store.upload_part(
        "demo", "multipart", upload.upload_id, 1, b"same-"
    )
    last = store.upload_part(
        "demo", "multipart", upload.upload_id, 2, b"bytes"
    )
    multipart = store.complete_multipart_upload(
        "demo", "multipart", upload.upload_id, [first, last]
    )

    print(f"same body: {single.body == multipart.body}")
    print(f"single PUT ETag: {single.etag}")
    print(f"multipart ETag: {multipart.etag}")
    print(f"ETags differ: {single.etag != multipart.etag}")
