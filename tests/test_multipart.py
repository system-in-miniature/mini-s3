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
