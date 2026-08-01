"""Listing tests make the directory illusion and ordering observable."""

from pathlib import Path

import pytest

from minis3 import InvalidContinuationToken, MiniS3


def _populated_store(root: Path) -> MiniS3:
    store = MiniS3(root)
    store.create_bucket("b")
    for key in ("a.txt", "photos/2025/a.jpg", "photos/2026/b.jpg", "raw"):
        store.put_object("b", key, key.encode())
    return store


def test_delimiter_derives_common_prefixes_from_flat_keys(tmp_path: Path) -> None:
    store = _populated_store(tmp_path)

    root = store.list_objects("b", delimiter="/")
    photos = store.list_objects("b", prefix="photos/", delimiter="/")
    flat = store.list_objects("b", prefix="photos/")

    assert [item.key for item in root.contents] == ["a.txt", "raw"]
    assert root.common_prefixes == ("photos/",)
    assert photos.common_prefixes == ("photos/2025/", "photos/2026/")
    assert [item.key for item in flat.contents] == [
        "photos/2025/a.jpg",
        "photos/2026/b.jpg",
    ]


def test_pagination_counts_contents_and_prefixes_and_token_is_opaque(
    tmp_path: Path,
) -> None:
    store = _populated_store(tmp_path)
    first = store.list_objects("b", delimiter="/", max_keys=2)
    second = store.list_objects(
        "b", delimiter="/", max_keys=2, continuation_token=first.next_token
    )

    assert first.key_count == 2
    assert first.next_token is not None
    assert "photos/" not in first.next_token
    assert {
        *(item.key for item in first.contents),
        *first.common_prefixes,
        *(item.key for item in second.contents),
        *second.common_prefixes,
    } == {"a.txt", "photos/", "raw"}
    assert second.next_token is None


def test_current_listing_hides_key_behind_delete_marker(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    store.put_object("b", "hidden", b"value")
    store.delete_object("b", "hidden")

    assert store.list_objects("b").contents == ()


def test_version_listing_flattens_versions_and_marks_latest(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    one = store.put_object("b", "a", b"one")
    two = store.put_object("b", "a", b"two")
    marker = store.delete_object("b", "a")

    items = store.list_object_versions("b").versions

    assert [item.version_id for item in items] == [
        marker.version_id,
        two.version_id,
        one.version_id,
    ]
    assert [item.is_latest for item in items] == [True, False, False]
    assert items[0].is_delete_marker is True


def test_malformed_or_query_mismatched_tokens_are_rejected(tmp_path: Path) -> None:
    store = _populated_store(tmp_path)
    first = store.list_objects("b", max_keys=1)

    with pytest.raises(InvalidContinuationToken):
        store.list_objects("b", continuation_token="not-base64!")
    with pytest.raises(InvalidContinuationToken):
        store.list_objects(
            "b", prefix="different", continuation_token=first.next_token
        )
