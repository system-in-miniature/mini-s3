"""Multipart tests pin invisible staging and S3's composite ETag trap."""

from hashlib import md5
from pathlib import Path

import pytest

from minis3 import (
    EntityTooSmall,
    InvalidPart,
    InvalidPartOrder,
    MiniS3,
    NoSuchKey,
    NoSuchUpload,
    SequenceCounter,
    content_etag,
)


def _md5(payload: bytes) -> bytes:
    return md5(payload, usedforsecurity=False).digest()


def test_multipart_is_invisible_until_ordered_atomic_complete(
    tmp_path: Path,
) -> None:
    store = MiniS3(tmp_path, counter=SequenceCounter(), minimum_part_size=3)
    store.create_bucket("b")
    upload = store.create_multipart_upload("b", "movie")
    second = store.upload_part("b", "movie", upload.upload_id, 2, b"end")
    first = store.upload_part("b", "movie", upload.upload_id, 1, b"abc")

    with pytest.raises(NoSuchKey):
        store.get_object("b", "movie")
    assert store.list_objects("b").contents == ()

    completed = store.complete_multipart_upload(
        "b", "movie", upload.upload_id, [first, second]
    )

    expected = md5(_md5(b"abc") + _md5(b"end"), usedforsecurity=False).hexdigest()
    assert completed.body == b"abcend"
    assert completed.etag == f'"{expected}-2"'
    assert completed.etag != content_etag(completed.body)
    assert [item.key for item in store.list_objects("b").contents] == ["movie"]


def test_uploading_same_part_number_replaces_the_staged_part(tmp_path: Path) -> None:
    store = MiniS3(tmp_path, minimum_part_size=3)
    store.create_bucket("b")
    upload = store.create_multipart_upload("b", "k")
    store.upload_part("b", "k", upload.upload_id, 1, b"old")
    first = store.upload_part("b", "k", upload.upload_id, 1, b"new")
    last = store.upload_part("b", "k", upload.upload_id, 2, b"x")

    completed = store.complete_multipart_upload(
        "b", "k", upload.upload_id, [first, last]
    )

    assert completed.body == b"newx"


def test_complete_validates_order_presence_etag_and_nonfinal_size(
    tmp_path: Path,
) -> None:
    store = MiniS3(tmp_path, minimum_part_size=3)
    store.create_bucket("b")
    upload = store.create_multipart_upload("b", "k")
    small = store.upload_part("b", "k", upload.upload_id, 1, b"x")
    final = store.upload_part("b", "k", upload.upload_id, 2, b"last")

    with pytest.raises(InvalidPartOrder):
        store.complete_multipart_upload(
            "b", "k", upload.upload_id, [final, small]
        )
    with pytest.raises(InvalidPart):
        store.complete_multipart_upload(
            "b",
            "k",
            upload.upload_id,
            [(1, '"00000000000000000000000000000000"'), final],
        )
    with pytest.raises(InvalidPart):
        store.complete_multipart_upload(
            "b", "k", upload.upload_id, [(3, final.etag)]
        )
    with pytest.raises(EntityTooSmall):
        store.complete_multipart_upload(
            "b", "k", upload.upload_id, [small, final]
        )

    # A small part is legal when the completion manifest makes it the last.
    completed = store.complete_multipart_upload(
        "b", "k", upload.upload_id, [small]
    )
    assert completed.body == b"x"


def test_abort_removes_upload_and_restart_preserves_unfinished_parts(
    tmp_path: Path,
) -> None:
    store = MiniS3(tmp_path, minimum_part_size=3)
    store.create_bucket("b")
    upload = store.create_multipart_upload("b", "k")
    first = store.upload_part("b", "k", upload.upload_id, 1, b"abc")

    reopened = MiniS3(tmp_path, minimum_part_size=3)
    last = reopened.upload_part("b", "k", upload.upload_id, 2, b"x")
    reopened.abort_multipart_upload("b", "k", upload.upload_id)

    with pytest.raises(NoSuchUpload):
        reopened.complete_multipart_upload(
            "b", "k", upload.upload_id, [first, last]
        )
    assert not list(tmp_path.rglob(upload.upload_id))


def test_upload_identity_and_part_number_are_validated(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    upload = store.create_multipart_upload("b", "right")

    with pytest.raises(NoSuchUpload):
        store.upload_part("b", "wrong", upload.upload_id, 1, b"x")
    with pytest.raises(ValueError):
        store.upload_part("b", "right", upload.upload_id, 0, b"x")
    with pytest.raises(ValueError):
        store.upload_part("b", "right", upload.upload_id, 10_001, b"x")

