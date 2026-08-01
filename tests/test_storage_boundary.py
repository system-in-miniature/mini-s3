"""Focused contract for manifest publication before service wiring."""

from minis3.bucket import Bucket, SequenceCounter, VersioningState
from minis3.storage import DiskStorage


def test_disk_storage_publishes_and_recovers_one_complete_bucket(tmp_path) -> None:
    storage = DiskStorage(tmp_path)
    bucket = Bucket("b", versioning=VersioningState.ENABLED)
    version = bucket.put("key", b"value", SequenceCounter())

    storage.create_bucket(Bucket("b"))
    storage.persist_bucket(bucket)
    recovered, maximum_sequence = DiskStorage(tmp_path).load_buckets()

    assert recovered["b"].get("key") == version
    assert maximum_sequence == version.sequence
    assert not list(tmp_path.rglob("*.tmp-*"))
