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

