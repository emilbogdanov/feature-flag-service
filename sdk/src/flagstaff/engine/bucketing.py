import hashlib
from typing import Final

# Rollout weights are counted in buckets: 1_000 buckets are 1%, so a rollout can move in
# steps of 0.001%.
BUCKET_COUNT: Final = 100_000


def bucket(flag_key: str, user_key: str) -> int:
    # SHA-256 rather than hash(): the server and every SDK process must put a user in the same
    # bucket, and hash() is salted per process. The flag key is hashed in so that the first 10%
    # of one rollout aren't also the first 10% of every other. Flag keys can't contain ":", so
    # two different (flag, user) pairs never hash the same input. A key decoded from JSON can hold
    # a lone surrogate, which strict UTF-8 refuses to encode; surrogatepass still gives it a bucket.
    digest = hashlib.sha256(f"{flag_key}:{user_key}".encode("utf-8", "surrogatepass")).digest()
    return int.from_bytes(digest[:8]) % BUCKET_COUNT
