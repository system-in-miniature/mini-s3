# Lab: The Multipart ETag Mystery

[中文版](../zh/labs/multipart-etag.md)

Run:

```bash
uv run python labs/lab_multipart_etag.py
```

The lab stores `same-bytes` once with a single PUT and once as two multipart
parts. Both GET bodies compare equal, but their ETags do not:

```text
same body: True
single PUT ETag: "e1d44c23b69953b35433ff067798318a"
multipart ETag: "05888a49b792dfb72298daafe3807667-2"
ETags differ: True
```

The multipart formula is not `md5(complete body)`. It is
`md5(part-1 MD5 binary digest || part-2 MD5 binary digest)-2`. Hashing the
hexadecimal digest text would produce another value and is the classic bug
this experiment is designed to expose.

The lab lowers MiniS3's configurable minimum part size to three bytes so it can
remain tiny. Production S3's normal minimum for every completed part except
the last is 5 MiB; MiniS3 uses that value by default.
