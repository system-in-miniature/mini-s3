"""Public, S3-shaped domain errors without an HTTP dependency."""


class MiniS3Error(Exception):
    """Base class for errors callers may translate to protocol responses."""


class BucketAlreadyExists(MiniS3Error):
    """The requested bucket name is already present."""


class NoSuchBucket(MiniS3Error):
    """The requested bucket does not exist."""


class BucketNotEmpty(MiniS3Error):
    """A bucket with live records or retained versions cannot be deleted."""


class NoSuchKey(MiniS3Error):
    """The current key is absent or hidden by a delete marker (HTTP 404)."""


class NoSuchVersion(MiniS3Error):
    """The requested version id is not retained for this key."""


class InvalidContinuationToken(MiniS3Error):
    """The list continuation token was malformed or belongs to another query."""


class NoSuchUpload(MiniS3Error):
    """The addressed multipart upload does not exist or no longer exists."""


class InvalidPart(MiniS3Error):
    """A completion entry names a missing part or the wrong part ETag."""


class InvalidPartOrder(MiniS3Error):
    """Multipart completion entries were not in strictly ascending order."""


class EntityTooSmall(MiniS3Error):
    """A non-final multipart part is below the configured minimum size."""


class PreconditionFailed(MiniS3Error):
    """An If-Match condition failed (the S3-shaped HTTP 412 outcome)."""


class NotModified(MiniS3Error):
    """An If-None-Match condition matched (the HTTP 304 control outcome)."""
