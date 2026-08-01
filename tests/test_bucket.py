"""Focused contracts for the bucket aggregate before service wiring."""

import pytest

from minis3.bucket import Bucket, SequenceCounter, VersioningState


def test_bucket_owns_versioning_transitions_and_deterministic_ids() -> None:
    bucket = Bucket("b")
    counter = SequenceCounter()

    null = bucket.put("key", b"before", counter)
    bucket.set_versioning(VersioningState.ENABLED)
    named = bucket.put("key", b"after", counter)
    bucket.set_versioning(VersioningState.SUSPENDED)

    assert (null.version_id, null.storage_id) == ("null", "e00000001")
    assert (named.version_id, named.storage_id) == ("v00000002", "e00000002")
    assert bucket.get("key").body == b"after"
    with pytest.raises(ValueError):
        bucket.set_versioning(VersioningState.UNVERSIONED)
