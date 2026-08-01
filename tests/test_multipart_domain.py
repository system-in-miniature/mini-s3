"""Focused contract for multipart validation before storage orchestration."""

from hashlib import md5

import pytest

from minis3.errors import EntityTooSmall, InvalidPartOrder
from minis3.multipart import StagedPart, validate_completion


def test_completion_validation_orders_parts_and_hashes_binary_digests() -> None:
    first = StagedPart(1, b"abc")
    last = StagedPart(2, b"x")
    staged = {1: first, 2: last}

    selected, etag = validate_completion(
        staged,
        [first.receipt, last.receipt],
        minimum_part_size=3,
    )

    binary_digests = b"".join(
        md5(part.body, usedforsecurity=False).digest() for part in selected
    )
    expected = md5(binary_digests, usedforsecurity=False).hexdigest()
    assert selected == (first, last)
    assert etag == f'"{expected}-2"'

    with pytest.raises(InvalidPartOrder):
        validate_completion(
            staged,
            [last.receipt, first.receipt],
            minimum_part_size=3,
        )
    with pytest.raises(EntityTooSmall):
        validate_completion(
            {1: StagedPart(1, b"a"), 2: last},
            [StagedPart(1, b"a").receipt, last.receipt],
            minimum_part_size=3,
        )
