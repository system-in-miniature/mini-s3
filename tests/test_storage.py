"""Disk tests pin the manifest publication crash boundary."""

from pathlib import Path

import pytest

from minis3 import InjectedCrash, MiniS3, NoSuchKey, SequenceCounter


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


def test_recovery_removes_spurious_tmp_files(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    stray = next((tmp_path / "buckets").iterdir()) / "manifest.json.tmp-stray"
    stray.write_text("partial")

    MiniS3(tmp_path)

    assert not stray.exists()
