"""Pure HTTP-style ETag precondition evaluation.

The service evaluates these functions while holding its mutation lock. That
placement matters: checking an ETag and publishing a replacement must be one
serialized compare-and-swap operation, not two individually safe calls.
"""

from __future__ import annotations

from .errors import NotModified, PreconditionFailed


def etag_matches(condition: str, current_etag: str | None) -> bool:
    """Return whether a simplified ETag header matches the current object."""

    candidates = tuple(item.strip() for item in condition.split(","))
    if "*" in candidates:
        return current_etag is not None
    return current_etag is not None and current_etag in candidates


def require_if_match(current_etag: str | None, condition: str | None) -> None:
    """Raise S3's named 412 outcome when If-Match is not satisfied."""

    if condition is not None and not etag_matches(condition, current_etag):
        raise PreconditionFailed(condition)


def require_if_none_match(
    current_etag: str | None, condition: str | None
) -> None:
    """Raise the body-less 304 control outcome when a cached ETag matches."""

    if condition is not None and etag_matches(condition, current_etag):
        raise NotModified(condition)
