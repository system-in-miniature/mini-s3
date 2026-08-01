"""Lifecycle rules are pure decisions applied only by an explicit clocked tick."""

from pathlib import Path

import pytest

from minis3 import (
    ExpirationRule,
    LifecycleActionKind,
    MiniS3,
    NoSuchKey,
    NoSuchVersion,
    VersioningState,
    evaluate_expiration,
)


class ManualClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_rule_evaluation_is_pure_prefix_filtered_and_boundary_inclusive(
    tmp_path: Path,
) -> None:
    clock = ManualClock()
    store = MiniS3(tmp_path, clock=clock)
    store.create_bucket("b")
    store.set_bucket_versioning("b", VersioningState.ENABLED)
    store.put_object("b", "logs/old", b"old")
    store.put_object("b", "keep/old", b"old")
    snapshot = store._buckets["b"].records
    rule = ExpirationRule("logs", prefix="logs/", expire_current_after=10)

    assert evaluate_expiration(snapshot, [rule], now=9.999) == ()
    actions = evaluate_expiration(snapshot, [rule], now=10)

    assert [(action.key, action.kind) for action in actions] == [
        ("logs/old", LifecycleActionKind.EXPIRE_CURRENT)
    ]
    assert store.get_object("b", "logs/old").body == b"old"


def test_tick_expires_current_to_marker_and_noncurrent_physically(
    tmp_path: Path,
) -> None:
    clock = ManualClock()
    store = MiniS3(tmp_path, clock=clock)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    old = store.put_object("b", "k", b"old")
    clock.now = 5
    current = store.put_object("b", "k", b"current")
    rule = ExpirationRule(
        "expire",
        expire_current_after=10,
        expire_noncurrent_after=12,
    )

    clock.now = 12
    first_actions = store.lifecycle_tick("b", [rule])
    assert [action.kind for action in first_actions] == [
        LifecycleActionKind.EXPIRE_NONCURRENT
    ]
    with pytest.raises(NoSuchVersion):
        store.get_object("b", "k", version_id=old.version_id)
    assert store.get_object("b", "k") == current

    clock.now = 15
    second_actions = store.lifecycle_tick("b", [rule])
    assert [action.kind for action in second_actions] == [
        LifecycleActionKind.EXPIRE_CURRENT
    ]
    with pytest.raises(NoSuchKey):
        store.get_object("b", "k")
    history = store.list_object_versions("b").versions
    assert history[0].is_delete_marker is True
    assert history[1].version_id == current.version_id


def test_tick_uses_injected_time_and_persists_timestamps_across_restart(
    tmp_path: Path,
) -> None:
    clock = ManualClock(100)
    store = MiniS3(tmp_path, clock=clock)
    store.create_bucket("b")
    store.set_bucket_versioning("b", "enabled")
    version = store.put_object("b", "k", b"value")
    assert version.created_at == 100

    reopened_clock = ManualClock(109)
    reopened = MiniS3(tmp_path, clock=reopened_clock)
    rule = ExpirationRule("ten-seconds", expire_current_after=10)
    assert reopened.lifecycle_tick("b", [rule]) == ()

    reopened_clock.now = 110
    assert reopened.lifecycle_tick("b", [rule])[0].kind is (
        LifecycleActionKind.EXPIRE_CURRENT
    )


def test_expiration_rule_rejects_empty_or_negative_policy() -> None:
    with pytest.raises(ValueError):
        ExpirationRule("empty")
    with pytest.raises(ValueError):
        ExpirationRule("negative", expire_current_after=-1)

