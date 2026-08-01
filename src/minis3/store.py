"""Public service facade joining buckets, object state, and list projections."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from threading import RLock

from .bucket import Bucket, SequenceCounter, VersioningState
from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket
from .model import ObjectVersion, Version
from .storage import DiskStorage


class MiniS3:
    """A deterministic collection of strongly consistent buckets."""

    def __init__(
        self,
        root: str | Path,
        *,
        counter: Callable[[], int] | None = None,
        crash_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.root = Path(root)
        self._counter = counter or SequenceCounter()
        self._storage = DiskStorage(root, crash_injector=crash_injector)
        self._buckets, maximum_sequence = self._storage.load_buckets()
        ensure = getattr(self._counter, "ensure_at_least", None)
        if ensure is not None:
            ensure(maximum_sequence + 1)
        self._lock = RLock()


    def create_bucket(self, name: str) -> None:
        with self._lock:
            if name in self._buckets:
                raise BucketAlreadyExists(name)
            bucket = Bucket(name)
            self._storage.create_bucket(bucket)
            self._buckets[name] = bucket


    def delete_bucket(self, name: str) -> None:
        with self._lock:
            bucket = self._bucket(name)
            if bucket.records:
                raise BucketNotEmpty(name)
            self._storage.delete_bucket(name)
            del self._buckets[name]


    def set_bucket_versioning(
        self, name: str, state: VersioningState | str
    ) -> None:
        with self._lock:
            candidate = deepcopy(self._bucket(name))
            candidate.set_versioning(state)
            self._storage.persist_bucket(candidate)
            self._buckets[name] = candidate


    def put_object(self, bucket: str, key: str, body: bytes) -> Version:
        with self._lock:
            candidate = deepcopy(self._bucket(bucket))
            result = candidate.put(key, body, self._counter)
            self._storage.persist_bucket(candidate)
            self._buckets[bucket] = candidate
            return result


    def get_object(
        self, bucket: str, key: str, *, version_id: str | None = None
    ) -> Version:
        with self._lock:
            return self._bucket(bucket).get(key, version_id)


    def head_object(
        self, bucket: str, key: str, *, version_id: str | None = None
    ) -> Version:
        """Return object metadata; M1 reuses the immutable Version value."""

        return self.get_object(bucket, key, version_id=version_id)


    def delete_object(
        self, bucket: str, key: str, *, version_id: str | None = None
    ) -> ObjectVersion | None:
        with self._lock:
            candidate = deepcopy(self._bucket(bucket))
            result = candidate.delete(key, self._counter, version_id)
            self._storage.persist_bucket(candidate)
            self._buckets[bucket] = candidate
            return result


    def _bucket(self, name: str) -> Bucket:
        try:
            return self._buckets[name]
        except KeyError as exc:
            raise NoSuchBucket(name) from exc

