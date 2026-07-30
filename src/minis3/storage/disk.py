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
from ..errors import NoSuchUpload
from ..model import DeleteMarker, ObjectRecord, ObjectVersion, Version
from ..multipart import MultipartUpload, StagedPart
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
            maximum_sequence = max(
                maximum_sequence, self._recover_uploads(child, bucket)
            )
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
        durable_mkdir(temporary / "uploads", parents=False)
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

    def create_multipart_upload(self, upload: MultipartUpload) -> None:
        """Durably create private staging that no object listing consults."""

        bucket_directory = self._bucket_directory(upload.bucket)
        uploads = bucket_directory / "uploads"
        durable_mkdir(uploads)
        directory = self._upload_directory(bucket_directory, upload.upload_id)
        durable_mkdir(directory, parents=False)
        durable_mkdir(directory / "parts", parents=False)
        metadata = {
            "format_version": 1,
            "bucket": upload.bucket,
            "key": upload.key,
            "upload_id": upload.upload_id,
            "sequence": upload.sequence,
            "initiated_at": upload.initiated_at,
        }
        atomic_write(
            directory / "upload.json",
            json.dumps(
                metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode(),
        )

    def write_multipart_part(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        part: StagedPart,
    ) -> None:
        """Atomically add or replace one durable staged part."""

        self.load_multipart_upload(bucket, key, upload_id)
        directory = self._upload_directory(
            self._bucket_directory(bucket), upload_id
        )
        atomic_write(directory / "parts" / f"{part.part_number:05d}.data", part.body)

    def load_multipart_upload(
        self, bucket: str, key: str, upload_id: str
    ) -> tuple[MultipartUpload, dict[int, StagedPart]]:
        """Reload one upload and all completely published part files."""

        directory = self._upload_directory(
            self._bucket_directory(bucket), upload_id
        )
        metadata_path = directory / "upload.json"
        if not metadata_path.exists():
            raise NoSuchUpload(upload_id)
        metadata = json.loads(metadata_path.read_text())
        if (
            metadata.get("format_version") != 1
            or metadata.get("bucket") != bucket
            or metadata.get("key") != key
            or metadata.get("upload_id") != upload_id
        ):
            raise NoSuchUpload(upload_id)
        upload = MultipartUpload(
            bucket=metadata["bucket"],
            key=metadata["key"],
            upload_id=metadata["upload_id"],
            sequence=metadata["sequence"],
            initiated_at=metadata["initiated_at"],
        )
        parts: dict[int, StagedPart] = {}
        for path in sorted((directory / "parts").glob("*.data")):
            try:
                part_number = int(path.stem)
            except ValueError:
                continue
            parts[part_number] = StagedPart(part_number, path.read_bytes())
        return upload, parts

    def remove_multipart_upload(
        self, bucket: str, key: str, upload_id: str
    ) -> None:
        """Remove staging through a rename so partial deletion is recoverable."""

        self.load_multipart_upload(bucket, key, upload_id)
        bucket_directory = self._bucket_directory(bucket)
        source = self._upload_directory(bucket_directory, upload_id)
        tombstone = source.with_name(f".deleted-{upload_id}")
        os.replace(source, tombstone)
        fsync_directory(tombstone.parent)
        shutil.rmtree(tombstone)
        fsync_directory(tombstone.parent)

    def _bucket_directory(self, name: str) -> Path:
        return self.buckets_root / _encoded_name(name)

    def _upload_directory(
        self, bucket_directory: Path, upload_id: str
    ) -> Path:
        if (
            not upload_id.startswith("u")
            or not upload_id[1:].isdigit()
            or len(upload_id) != 9
        ):
            raise NoSuchUpload(upload_id)
        return bucket_directory / "uploads" / upload_id

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
            "created_at": item.created_at,
        }
        if isinstance(item, Version):
            atomic_write(directory / f"{item.storage_id}.data", item.body)
            metadata.update(
                etag=item.etag,
                size=item.size,
                multipart_upload_id=item.multipart_upload_id,
            )
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
                created_at=metadata.get("created_at", 0.0),
            )
        body = (directory / f"{storage_id}.data").read_bytes()
        version = Version(
            version_id=metadata["version_id"],
            storage_id=storage_id,
            sequence=metadata["sequence"],
            body=body,
            etag=metadata["etag"],
            created_at=metadata.get("created_at", 0.0),
            multipart_upload_id=metadata.get("multipart_upload_id"),
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

    def _recover_uploads(self, directory: Path, bucket: Bucket) -> int:
        """Remove completed/torn staging and return its largest sequence."""

        uploads = directory / "uploads"
        durable_mkdir(uploads)
        completed = {
            item.multipart_upload_id
            for record in bucket.records.values()
            for item in record.versions
            if isinstance(item, Version) and item.multipart_upload_id is not None
        }
        maximum_sequence = 0
        changed = False
        for child in sorted(uploads.iterdir()):
            if child.name.startswith((".tmp-", ".deleted-")):
                shutil.rmtree(child)
                changed = True
                continue
            metadata_path = child / "upload.json"
            if not child.is_dir() or not metadata_path.exists():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                changed = True
                continue
            metadata = json.loads(metadata_path.read_text())
            maximum_sequence = max(maximum_sequence, metadata["sequence"])
            if child.name in completed:
                shutil.rmtree(child)
                changed = True
                continue
            for temporary in child.rglob("*.tmp-*"):
                temporary.unlink()
                changed = True
        if changed:
            fsync_directory(uploads)
        return maximum_sequence
