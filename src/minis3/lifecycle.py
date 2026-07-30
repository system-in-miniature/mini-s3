"""Planned M2 deterministic lifecycle rule evaluation.

M2 will use an injected clock plus an explicit ``tick`` to expire current and
non-current versions. It will not use wall-clock calls, background threads, or
storage-class transitions.
"""

