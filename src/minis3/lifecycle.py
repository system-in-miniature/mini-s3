"""Pure lifecycle expiration decisions for an explicit manual tick.

Evaluation reads an immutable-style snapshot and returns actions; it never
mutates records or reads a clock. The service injects ``now`` and applies the
actions only when the caller explicitly requests a tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .model import ObjectRecord, Version


@dataclass(frozen=True, slots=True)
class ExpirationRule:
    """Age thresholds for matching current and noncurrent data versions."""

    rule_id: str
    prefix: str = ""
    expire_current_after: float | None = None
    expire_noncurrent_after: float | None = None

    def __post_init__(self) -> None:
        thresholds = (self.expire_current_after, self.expire_noncurrent_after)
        if all(value is None for value in thresholds):
            raise ValueError("an expiration rule needs at least one threshold")
        if any(value is not None and value < 0 for value in thresholds):
            raise ValueError("expiration ages must be non-negative")


class LifecycleActionKind(StrEnum):
    """The two deliberately small M2 lifecycle transitions."""

    EXPIRE_CURRENT = "expire_current"
    EXPIRE_NONCURRENT = "expire_noncurrent"


@dataclass(frozen=True, slots=True)
class LifecycleAction:
    """One deterministic mutation selected by a named rule."""

    rule_id: str
    key: str
    version_id: str
    kind: LifecycleActionKind


def _old_enough(created_at: float, threshold: float | None, now: float) -> bool:
    return threshold is not None and now - created_at >= threshold


def evaluate_expiration(
    records: dict[str, ObjectRecord],
    rules: list[ExpirationRule] | tuple[ExpirationRule, ...],
    *,
    now: float,
) -> tuple[LifecycleAction, ...]:
    """Return de-duplicated actions without changing the supplied records."""

    actions: list[LifecycleAction] = []
    selected: set[tuple[str, str, LifecycleActionKind]] = set()
    for key in sorted(records):
        record = records[key]
        if not record.versions:
            continue
        for rule in rules:
            if not key.startswith(rule.prefix):
                continue
            current = record.versions[0]
            identity = (key, current.version_id, LifecycleActionKind.EXPIRE_CURRENT)
            if (
                isinstance(current, Version)
                and identity not in selected
                and _old_enough(
                    current.created_at, rule.expire_current_after, now
                )
            ):
                selected.add(identity)
                actions.append(
                    LifecycleAction(rule.rule_id, key, current.version_id, identity[2])
                )
            for version in record.versions[1:]:
                identity = (
                    key,
                    version.version_id,
                    LifecycleActionKind.EXPIRE_NONCURRENT,
                )
                if (
                    isinstance(version, Version)
                    and identity not in selected
                    and _old_enough(
                        version.created_at, rule.expire_noncurrent_after, now
                    )
                ):
                    selected.add(identity)
                    actions.append(
                        LifecycleAction(
                            rule.rule_id, key, version.version_id, identity[2]
                        )
                    )
    return tuple(actions)
