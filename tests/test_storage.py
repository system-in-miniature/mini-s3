"""Disk tests pin the manifest publication crash boundary."""

from pathlib import Path

import pytest

from minis3 import InjectedCrash, MiniS3, NoSuchKey, SequenceCounter
from minis3.bucket import Bucket
from minis3.storage import atomic, disk
from minis3.storage.disk import DiskStorage


class CrashOnce:
    def __init__(self, target: str) -> None:
        self.target = target
        self.used = False

    def __call__(self, point: str) -> None:
        if point == self.target and not self.used:
            self.used = True
            raise InjectedCrash(point)


def test_restart_restores_versions_bodies_and_counter(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    first = store.put_object("b", "k", b"one")

    reopened = MiniS3(tmp_path)
    second = reopened.put_object("b", "k", b"two")

    assert reopened.get_object("b", "k", version_id=first.version_id).body == b"one"
    assert second.version_id != first.version_id


def test_crash_before_manifest_publish_leaves_old_state(tmp_path: Path) -> None:
    MiniS3(tmp_path).create_bucket("b")
    crashing = MiniS3(
        tmp_path,
        counter=SequenceCounter(10),
        crash_injector=CrashOnce("before_manifest_publish"),
    )

    with pytest.raises(InjectedCrash):
        crashing.put_object("b", "new", b"value")

    reopened = MiniS3(tmp_path)
    with pytest.raises(NoSuchKey):
        reopened.get_object("b", "new")
    assert not list(tmp_path.rglob("*.tmp-*"))
    assert not list(tmp_path.rglob("e00000010.*"))


@pytest.mark.parametrize(
    "crash_point",
    [
        "after_object_directory_create",
        "after_object_directory_parent_fsync",
        "before_manifest_publish",
    ],
)
def test_crash_before_manifest_publication_matrix_leaves_old_state(
    tmp_path: Path,
    crash_point: str,
) -> None:
    MiniS3(tmp_path).create_bucket("b")
    crashing = MiniS3(
        tmp_path,
        counter=SequenceCounter(10),
        crash_injector=CrashOnce(crash_point),
    )

    with pytest.raises(InjectedCrash):
        crashing.put_object("b", "new", b"value")

    reopened = MiniS3(tmp_path)
    with pytest.raises(NoSuchKey):
        reopened.get_object("b", "new")
    assert not list(tmp_path.rglob("*.tmp-*"))
    assert not list(tmp_path.rglob("e00000010.*"))


def test_crash_after_manifest_publish_exposes_complete_new_state(
    tmp_path: Path,
) -> None:
    MiniS3(tmp_path).create_bucket("b")
    crashing = MiniS3(
        tmp_path,
        counter=SequenceCounter(10),
        crash_injector=CrashOnce("after_manifest_publish"),
    )

    with pytest.raises(InjectedCrash):
        crashing.put_object("b", "new", b"value")

    reopened = MiniS3(tmp_path)
    visible = reopened.get_object("b", "new")
    assert visible.body == b"value"
    assert visible.etag == '"2063c1608d6e0baf80249c42e2be5804"'


def test_atomic_write_fsyncs_each_new_directory_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    real_fsync_directory = atomic.fsync_directory

    def recording_fsync_directory(path: Path) -> None:
        calls.append(path)
        real_fsync_directory(path)

    monkeypatch.setattr(atomic, "fsync_directory", recording_fsync_directory)

    atomic.atomic_write(tmp_path / "one" / "two" / "value", b"payload")

    assert calls == [tmp_path, tmp_path / "one", tmp_path / "one" / "two"]


def test_storage_and_bucket_directory_creation_fsync_parent_chains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    real_fsync_directory = disk.fsync_directory

    def recording_fsync_directory(path: Path) -> None:
        calls.append(path)
        real_fsync_directory(path)

    monkeypatch.setattr(disk, "fsync_directory", recording_fsync_directory)
    monkeypatch.setattr(atomic, "fsync_directory", recording_fsync_directory)
    root = tmp_path / "new-root"
    storage = DiskStorage(root)
    storage.create_bucket(Bucket("b"))

    bucket_directory = storage._bucket_directory("b")
    temporary = storage.buckets_root / f".tmp-{bucket_directory.name}"
    assert tmp_path in calls
    assert calls.count(root) >= 1
    assert calls.count(storage.buckets_root) >= 2
    assert calls.count(temporary) >= 2


def test_recovery_removes_spurious_tmp_files(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    stray = next((tmp_path / "buckets").iterdir()) / "manifest.json.tmp-stray"
    stray.write_text("partial")

    MiniS3(tmp_path)

    assert not stray.exists()
