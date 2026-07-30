"""Disk layout, manifest publication, and startup recovery.

Layout::

    buckets/<encoded-bucket>/
      manifest.json
      objects/<sha256-key>/<storage-id>.json
      objects/<sha256-key>/<storage-id>.data

Artifacts are immutable and written first. ``manifest.json`` is written last,
so its atomic rename is the visibility linearization point. Recovery trusts
only manifest references and removes temporary or orphaned artifacts.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Callable
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

from ..bucket import Bucket, VersioningState
from ..model import DeleteMarker, ObjectRecord, ObjectVersion, Version
from .atomic import atomic_write, durable_mkdir, fsync_directory


def _encoded_name(name: str) -> str:
    if not name:
        raise ValueError("bucket name must not be empty")
    return urlsafe_b64encode(name.encode()).decode().rstrip("=")


def _object_directory(bucket_directory: Path, key: str) -> Path:
    return bucket_directory / "objects" / sha256(key.encode()).hexdigest()


class DiskStorage:
    """Own durable bucket directories and recover complete manifests."""

    def __init__(
        self,
        root: str | Path,
        *,
        crash_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.root = Path(root)
        self.buckets_root = self.root / "buckets"
        durable_mkdir(self.buckets_root)
        self._inject = crash_injector or (lambda _point: None)

    def load_buckets(self) -> tuple[dict[str, Bucket], int]:
        """Recover published buckets and return the maximum used sequence."""

        buckets: dict[str, Bucket] = {}
        maximum_sequence = 0
        for child in sorted(self.buckets_root.iterdir()):
            if child.name.startswith((".tmp-", ".deleted-")):
                shutil.rmtree(child)
                continue
            if not child.is_dir():
                continue
            manifest_path = child / "manifest.json"
            if not manifest_path.exists():
                shutil.rmtree(child)
                continue
            bucket = self._load_bucket(child)
            buckets[bucket.name] = bucket
            for record in bucket.records.values():
                for item in record.versions:
                    maximum_sequence = max(maximum_sequence, item.sequence)
            self._clean_bucket(child, bucket)
        fsync_directory(self.buckets_root)
        return buckets, maximum_sequence

    def create_bucket(self, bucket: Bucket) -> None:
        """Atomically make a fully initialized bucket directory visible."""

        final = self._bucket_directory(bucket.name)
        temporary = self.buckets_root / f".tmp-{final.name}"
        if temporary.exists():
            shutil.rmtree(temporary)
            fsync_directory(self.buckets_root)
        durable_mkdir(temporary, parents=False)
        durable_mkdir(temporary / "objects", parents=False)
        manifest = self._manifest_bytes(bucket)
        with (temporary / "manifest.json").open("wb") as handle:
            handle.write(manifest)
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(temporary)
        os.replace(temporary, final)
        fsync_directory(self.buckets_root)

    def delete_bucket(self, name: str) -> None:
        """Remove an empty bucket via a recoverable directory rename."""

        source = self._bucket_directory(name)
        tombstone = self.buckets_root / f".deleted-{source.name}"
        os.replace(source, tombstone)
        fsync_directory(self.buckets_root)
        shutil.rmtree(tombstone)
        fsync_directory(self.buckets_root)

    def persist_bucket(self, bucket: Bucket) -> None:
        """Write missing artifacts, then atomically publish their references."""

        directory = self._bucket_directory(bucket.name)
        for record in bucket.records.values():
            for item in record.versions:
                self._write_artifact(directory, record.key, item)

        # This hook models process death after durable artifacts but before the
        # only visibility-changing rename.
        self._inject("before_manifest_publish")
        atomic_write(directory / "manifest.json", self._manifest_bytes(bucket))
        self._inject("after_manifest_publish")
        self._clean_bucket(directory, bucket)

    def _bucket_directory(self, name: str) -> Path:
        return self.buckets_root / _encoded_name(name)

    def _manifest_bytes(self, bucket: Bucket) -> bytes:
        payload = {
            "format_version": 1,
            "name": bucket.name,
            "versioning": bucket.versioning.value,
            "records": {
                key: [item.storage_id for item in record.versions]
                for key, record in sorted(bucket.records.items())
            },
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()

    def _write_artifact(
        self, bucket_directory: Path, key: str, item: ObjectVersion
    ) -> None:
        directory = _object_directory(bucket_directory, key)
        if not directory.exists():
            directory.mkdir()
            self._inject("after_object_directory_create")
            fsync_directory(directory.parent)
            self._inject("after_object_directory_parent_fsync")
        metadata_path = directory / f"{item.storage_id}.json"
        if metadata_path.exists():
            return
        metadata: dict[str, object] = {
            "key": key,
            "kind": "delete_marker" if isinstance(item, DeleteMarker) else "version",
            "version_id": item.version_id,
            "storage_id": item.storage_id,
            "sequence": item.sequence,
        }
        if isinstance(item, Version):
            atomic_write(directory / f"{item.storage_id}.data", item.body)
            metadata.update(etag=item.etag, size=item.size)
        atomic_write(
            metadata_path,
            json.dumps(
                metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode(),
        )

    def _load_bucket(self, directory: Path) -> Bucket:
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("format_version") != 1:
            raise ValueError(f"unsupported manifest in {directory}")
        bucket = Bucket(
            name=manifest["name"],
            versioning=VersioningState(manifest["versioning"]),
        )
        for key, storage_ids in manifest["records"].items():
            versions = tuple(
                self._load_artifact(directory, key, storage_id)
                for storage_id in storage_ids
            )
            bucket.records[key] = ObjectRecord(key, versions)
        return bucket

    def _load_artifact(
        self, bucket_directory: Path, key: str, storage_id: str
    ) -> ObjectVersion:
        directory = _object_directory(bucket_directory, key)
        metadata = json.loads((directory / f"{storage_id}.json").read_text())
        if metadata["key"] != key or metadata["storage_id"] != storage_id:
            raise ValueError(f"artifact identity mismatch: {storage_id}")
        if metadata["kind"] == "delete_marker":
            return DeleteMarker(
                version_id=metadata["version_id"],
                storage_id=storage_id,
                sequence=metadata["sequence"],
            )
        body = (directory / f"{storage_id}.data").read_bytes()
        version = Version(
            version_id=metadata["version_id"],
            storage_id=storage_id,
            sequence=metadata["sequence"],
            body=body,
            etag=metadata["etag"],
        )
        if version.size != metadata["size"]:
            raise ValueError(f"artifact size mismatch: {storage_id}")
        return version

    def _clean_bucket(self, directory: Path, bucket: Bucket) -> None:
        for temporary in directory.glob("*.tmp-*"):
            temporary.unlink()
        referenced = {
            item.storage_id
            for record in bucket.records.values()
            for item in record.versions
        }
        objects = directory / "objects"
        if not objects.exists():
            return
        for path in sorted(objects.rglob("*")):
            if path.is_file() and ".tmp-" in path.name:
                path.unlink()
            elif path.is_file() and path.stem not in referenced:
                path.unlink()
        for path in sorted(objects.rglob("*"), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
