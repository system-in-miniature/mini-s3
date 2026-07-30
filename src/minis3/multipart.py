"""Planned M2 multipart-upload state machine.

M2 will add initiate/upload-part/complete/abort, minimum part-size checks,
ordered completion, invisible incomplete uploads, and multipart ETags of the
form ``md5(concatenated part md5 digests)-N``. M1 intentionally exposes no
partial API here: a placeholder implementation could be mistaken for atomic
multipart support.
"""

