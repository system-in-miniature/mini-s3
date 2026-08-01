"""Conditional requests turn current ETags into an object-level CAS token."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from minis3 import MiniS3, NoSuchKey, NotModified, PreconditionFailed


def test_get_if_none_match_has_304_semantics_and_if_match_has_412(
    tmp_path: Path,
) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    current = store.put_object("b", "k", b"value")

    with pytest.raises(NotModified):
        store.get_object("b", "k", if_none_match=current.etag)
    with pytest.raises(NotModified):
        store.get_object("b", "k", if_none_match="*")
    with pytest.raises(PreconditionFailed):
        store.get_object(
            "b", "k", if_match='"00000000000000000000000000000000"'
        )
    assert store.get_object("b", "k", if_match=current.etag) == current


def test_put_and_delete_if_match_compare_against_current_visible_etag(
    tmp_path: Path,
) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    initial = store.put_object("b", "k", b"old")
    winner = store.put_object("b", "k", b"new", if_match=initial.etag)

    with pytest.raises(PreconditionFailed):
        store.put_object("b", "k", b"stale", if_match=initial.etag)
    with pytest.raises(PreconditionFailed):
        store.delete_object("b", "k", if_match=initial.etag)

    removed = store.delete_object("b", "k", if_match=winner.etag)
    assert removed is None
    with pytest.raises(NoSuchKey):
        store.get_object("b", "k")


def test_if_match_wildcard_requires_a_current_visible_object(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")

    with pytest.raises(PreconditionFailed):
        store.put_object("b", "missing", b"x", if_match="*")
    with pytest.raises(PreconditionFailed):
        store.delete_object("b", "missing", if_match="*")

    store.put_object("b", "present", b"x")
    assert store.put_object("b", "present", b"y", if_match="*").body == b"y"


def test_two_conditional_writers_have_exactly_one_winner(tmp_path: Path) -> None:
    store = MiniS3(tmp_path)
    store.create_bucket("b")
    observed = store.put_object("b", "counter", b"0").etag
    barrier = Barrier(2)

    def writer(value: bytes) -> str:
        barrier.wait()
        try:
            store.put_object("b", "counter", value, if_match=observed)
        except PreconditionFailed:
            return "412"
        return "stored"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(writer, (b"writer-a", b"writer-b")))

    assert sorted(outcomes) == ["412", "stored"]
    assert store.get_object("b", "counter").body in {b"writer-a", b"writer-b"}

