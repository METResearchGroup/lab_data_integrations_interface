"""Decode AT Protocol timestamp identifiers (TIDs).

Post rkeys and repo revs are TIDs. The high 53 bits are microseconds since the
Unix epoch; the low 10 bits are a clock id. A record whose rkey TID matches
`created_at` was minted with that timestamp. A rev TID near `ingested_at` is
the commit that actually hit the firehose.
"""

from datetime import UTC, datetime

from experiments.jetstream_old_vs_new_posts_2026_08_18.constants import (
    TID_ALPHABET,
    TID_CLOCK_ID_BITS,
)


def decode_tid_microseconds(tid: str) -> int | None:
    """Return the timestamp in Unix microseconds, or None if `tid` is not a TID."""

    if len(tid) != 13:
        return None
    value = 0
    for char in tid:
        index = TID_ALPHABET.find(char)
        if index < 0:
            return None
        value = value * 32 + index
    return value >> TID_CLOCK_ID_BITS


def tid_datetime(tid: str) -> datetime | None:
    microseconds = decode_tid_microseconds(tid)
    if microseconds is None:
        return None
    return datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)


def rkey_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]
