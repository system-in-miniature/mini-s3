"""Executable contracts for MiniS3's flat object model."""

from dataclasses import FrozenInstanceError

import pytest

from minis3 import DeleteMarker, ObjectRecord, Version, content_etag


def test_etag_is_quoted_lowercase_content_md5() -> None:
    assert content_etag(b"hello") == '"5d41402abc4b2a76b9719d911017c592"'


def test_keys_are_opaque_even_when_they_contain_slashes() -> None:
    version = Version(
        version_id="null",
        storage_id="e00000001",
        sequence=1,
        body=b"x",
        etag=content_etag(b"x"),
    )
    record = ObjectRecord(key="/a//b/", versions=(version,))

    assert record.key == "/a//b/"
    assert record.versions == (version,)
    with pytest.raises(FrozenInstanceError):
        version.etag = "changed"  # type: ignore[misc]


def test_delete_marker_has_no_object_body() -> None:
    marker = DeleteMarker(
        version_id="v00000002", storage_id="e00000002", sequence=2
    )
    assert marker.is_delete_marker is True

