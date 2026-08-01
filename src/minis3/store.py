"""Public service facade joining buckets, object state, and list projections."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import time

from .conditional import require_if_match, require_if_none_match
from .bucket import Bucket, SequenceCounter, VersioningState
from .errors import BucketAlreadyExists, BucketNotEmpty, NoSuchBucket, NoSuchKey, NoSuchVersion
from .listing import ListObjectsResult, ListObjectVersionsResult, list_object_versions, list_objects
from .model import ObjectVersion, Version
from .multipart import (
    MAX_PART_NUMBER,
    MIN_PART_SIZE,
    CompletionEntry,
    MultipartPart,
    MultipartUpload,
    StagedPart,
    validate_completion,
)
from .storage import DiskStorage


class MiniS3:
    """A deterministic collection of strongly consistent buckets."""

    def __init__(
        self,
        root: str | Path,
        *,
        counter: Callable[[], int] | None = None,
        crash_injector: Callable[[str], None] | None = None,
        clock: Callable[[], float] | None = None,
        minimum_part_size: int = MIN_PART_SIZE,
    ) -> None:
        if minimum_part_size < 1:
            raise ValueError("minimum_part_size must be positive")
        self.root = Path(root)
        self._counter = counter or SequenceCounter()
        self._clock = clock or time
        self.minimum_part_size = minimum_part_size
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


    def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        *,
        if_match: str | None = None,
    ) -> Version:
        with self._lock:
            candidate = deepcopy(self._bucket(bucket))
            require_if_match(self._current_etag(candidate, key), if_match)
            result = candidate.put(
                key, body, self._counter, now=self._clock()
            )
            self._storage.persist_bucket(candidate)
            self._buckets[bucket] = candidate
            return result


    def get_object(
        self,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        if_match: str | None = None,
        if_none_match: str | None = None,
    ) -> Version:
        with self._lock:
            result = self._bucket(bucket).get(key, version_id)
            require_if_match(result.etag, if_match)
            require_if_none_match(result.etag, if_none_match)
            return result


    def head_object(
        self, bucket: str, key: str, *, version_id: str | None = None
    ) -> Version:
        """Return object metadata; M1 reuses the immutable Version value."""

        return self.get_object(bucket, key, version_id=version_id)


    def delete_object(
        self,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        if_match: str | None = None,
    ) -> ObjectVersion | None:
        with self._lock:
            candidate = deepcopy(self._bucket(bucket))
            require_if_match(
                self._addressed_etag(candidate, key, version_id), if_match
            )
            result = candidate.delete(
                key, self._counter, version_id, now=self._clock()
            )
            self._storage.persist_bucket(candidate)
            self._buckets[bucket] = candidate
            return result


    def list_objects(
        self,
        bucket: str,
        *,
        prefix: str = "",
        delimiter: str | None = None,
        max_keys: int = 1000,
        continuation_token: str | None = None,
    ) -> ListObjectsResult:
        with self._lock:
            return list_objects(
                self._bucket(bucket).records,
                prefix=prefix,
                delimiter=delimiter,
                max_keys=max_keys,
                continuation_token=continuation_token,
            )


    def list_object_versions(
        self, bucket: str, *, prefix: str = ""
    ) -> ListObjectVersionsResult:
        with self._lock:
            return list_object_versions(self._bucket(bucket).records, prefix=prefix)


    def create_multipart_upload(
        self, bucket: str, key: str
    ) -> MultipartUpload:
        """Initiate durable staging without adding a visible object record."""

        with self._lock:
            self._bucket(bucket)
            sequence = self._counter()
            upload = MultipartUpload(
                bucket=bucket,
                key=key,
                upload_id=f"u{sequence:08d}",
                sequence=sequence,
                initiated_at=self._clock(),
            )
            self._storage.create_multipart_upload(upload)
            return upload


    def upload_part(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        part_number: int,
        body: bytes,
    ) -> MultipartPart:
        """Durably add/replace a part; final-part size is decided at complete."""

        if not 1 <= part_number <= MAX_PART_NUMBER:
            raise ValueError(f"part_number must be between 1 and {MAX_PART_NUMBER}")
        with self._lock:
            self._bucket(bucket)
            part = StagedPart(part_number, bytes(body))
            self._storage.write_multipart_part(bucket, key, upload_id, part)
            return part.receipt


    def complete_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        parts: list[CompletionEntry] | tuple[CompletionEntry, ...],
    ) -> Version:
        """Validate, assemble, and publish through the bucket manifest rename."""

        with self._lock:
            self._bucket(bucket)
            _upload, staged = self._storage.load_multipart_upload(
                bucket, key, upload_id
            )
            selected, etag = validate_completion(
                staged, parts, minimum_part_size=self.minimum_part_size
            )
            body = b"".join(part.body for part in selected)
            candidate = deepcopy(self._bucket(bucket))
            result = candidate.put(
                key,
                body,
                self._counter,
                etag=etag,
                now=self._clock(),
                multipart_upload_id=upload_id,
            )
            self._storage.persist_bucket(candidate)
            self._buckets[bucket] = candidate
            self._storage.remove_multipart_upload(bucket, key, upload_id)
            return result


    def abort_multipart_upload(
        self, bucket: str, key: str, upload_id: str
    ) -> None:
        """Discard one incomplete upload without affecting any object."""

        with self._lock:
            self._bucket(bucket)
            self._storage.remove_multipart_upload(bucket, key, upload_id)


    @staticmethod
    def _current_etag(bucket: Bucket, key: str) -> str | None:
        try:
            return bucket.get(key).etag
        except NoSuchKey:
            return None


    @staticmethod
    def _addressed_etag(
        bucket: Bucket, key: str, version_id: str | None
    ) -> str | None:
        try:
            return bucket.get(key, version_id).etag
        except (NoSuchKey, NoSuchVersion):
            return None


    def _bucket(self, name: str) -> Bucket:
        try:
            return self._buckets[name]
        except KeyError as exc:
            raise NoSuchBucket(name) from exc

