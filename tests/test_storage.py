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
