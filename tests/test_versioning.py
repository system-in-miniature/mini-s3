"""Versioning is the central state-machine contract of M1."""

from pathlib import Path

import pytest

from minis3 import (
    BucketNotEmpty,
    MiniS3,
    NoSuchKey,
    NoSuchVersion,
    SequenceCounter,
    VersioningState,
)


def test_unversioned_put_replaces_null_and_delete_removes_it(tmp_path: Path) -> None:
    store = MiniS3(tmp_path, counter=SequenceCounter())
    store.create_bucket("photos")

    first = store.put_object("photos", "cat.jpg", b"first")
    second = store.put_object("photos", "cat.jpg", b"second")

    assert first.version_id == second.version_id == "null"
    assert store.get_object("photos", "cat.jpg").body == b"second"
    assert len(store.list_object_versions("photos").versions) == 1

    assert store.delete_object("photos", "cat.jpg") is None
    with pytest.raises(NoSuchKey):
        store.get_object("photos", "cat.jpg")


def test_enabled_puts_stack_and_delete_marker_hides_history(tmp_path: Path) -> None:
    store = MiniS3(tmp_path, counter=SequenceCounter())
    store.create_bucket("photos")
    null = store.put_object("photos", "cat.jpg", b"before")
    store.set_bucket_versioning("photos", VersioningState.ENABLED)
    first = store.put_object("photos", "cat.jpg", b"one")
    second = store.put_object("photos", "cat.jpg", b"two")
    marker = store.delete_object("photos", "cat.jpg")

    assert [null.version_id, first.version_id, second.version_id] == [
        "null",
        "v00000002",
        "v00000003",
    ]
    assert marker is not None and marker.version_id == "v00000004"
    with pytest.raises(NoSuchKey):
        store.get_object("photos", "cat.jpg")
    assert store.get_object(
        "photos", "cat.jpg", version_id=second.version_id
    ).body == b"two"
    assert store.head_object(
        "photos", "cat.jpg", version_id=first.version_id
    ).etag == first.etag


def test_specific_delete_removes_only_addressed_version(tmp_path: Path) -> None:
    store = MiniS3(tmp_path, counter=SequenceCounter())
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    store.put_object("b", "k", b"old")
    new = store.put_object("b", "k", b"new")

    removed = store.delete_object("b", "k", version_id=new.version_id)

    assert removed == new
    assert store.get_object("b", "k").body == b"old"
    with pytest.raises(NoSuchVersion):
        store.get_object("b", "k", version_id=new.version_id)


def test_suspended_put_replaces_null_but_preserves_named_history(
    tmp_path: Path,
) -> None:
    store = MiniS3(tmp_path, counter=SequenceCounter())
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    historical = store.put_object("b", "k", b"historical")
    store.set_bucket_versioning("b", "suspended")

    first_null = store.put_object("b", "k", b"null-one")
    second_null = store.put_object("b", "k", b"null-two")

    assert first_null.version_id == second_null.version_id == "null"
    assert store.get_object("b", "k").body == b"null-two"
    assert store.get_object(
        "b", "k", version_id=historical.version_id
    ).body == b"historical"
    assert [
        item.version_id for item in store.list_object_versions("b").versions
    ] == ["null", historical.version_id]


def test_latest_marker_is_404_even_when_older_data_exists(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    old = store.put_object("b", "k", b"still here")
    marker = store.delete_object("b", "k")

    with pytest.raises(NoSuchKey):
        store.head_object("b", "k")
    assert store.get_object("b", "k", version_id=old.version_id).body == b"still here"
    assert store.delete_object("b", "k", version_id=marker.version_id) == marker
    assert store.get_object("b", "k").body == b"still here"


def test_suspended_delete_replaces_null_with_null_marker(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    historical = store.put_object("b", "k", b"named")
    store.set_bucket_versioning("b", "suspended")
    store.put_object("b", "k", b"replaceable null")

    marker = store.delete_object("b", "k")

    assert marker is not None and marker.version_id == "null"
    with pytest.raises(NoSuchKey):
        store.get_object("b", "k")
    assert store.get_object(
        "b", "k", version_id=historical.version_id
    ).body == b"named"


def test_nonempty_bucket_cannot_be_deleted(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    store.put_object("b", "k", b"value")
    with pytest.raises(BucketNotEmpty):
        store.delete_bucket("b")
