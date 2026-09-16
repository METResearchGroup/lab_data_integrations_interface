import hashlib
import os
from datetime import UTC, datetime

import libipld
import pytest

from bluesky_backfill_app.fetch_repos.decode.records import decode
from bluesky_ingestion_jetstream.constants import FOLLOWS, LIKES, POSTS, RECORD_TYPES, REPOSTS

DID = "did:plc:example"
REV = "3mvj76icttp2q"
INGESTED_AT = datetime(2026, 9, 14, tzinfo=UTC)
CREATED_AT = "2026-08-01T12:00:00.000Z"
SUBJECT = {"uri": "at://did:plc:other/app.bsky.feed.post/abc", "cid": "bafysubject"}


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


class CarBuilder:
    def __init__(self):
        self.blocks = {}

    def add(self, value):
        data = libipld.encode_dag_cbor(value)
        cid = b"\x01q\x12 " + hashlib.sha256(data).digest()
        self.blocks[cid] = data
        return cid

    def node(self, entries, left=None):
        encoded = []
        previous = b""
        for key, value, right in entries:
            key = key.encode()
            shared = len(os.path.commonprefix([previous, key]))
            encoded.append({"p": shared, "k": key[shared:], "v": value, "t": right})
            previous = key
        return self.add({"l": left, "e": encoded})

    def build(self, data, did=DID, rev=REV):
        root = self.add({"did": did, "rev": rev, "data": data, "version": 3, "prev": None})
        header = libipld.encode_dag_cbor({"roots": [root], "version": 1})
        sections = [varint(len(header)) + header]
        sections += [varint(len(cid) + len(data)) + cid + data for cid, data in self.blocks.items()]
        return b"".join(sections)


def flat_car(records, **kwargs):
    builder = CarBuilder()
    entries = [(key, builder.add(record), None) for key, record in sorted(records.items())]
    return builder.build(builder.node(entries), **kwargs)


def like(created_at: str | None = CREATED_AT, **extra):
    return {"$type": "app.bsky.feed.like", "subject": SUBJECT, "createdAt": created_at} | extra


def test_decode_builds_a_row_per_record_type():
    car = flat_car(
        {
            "app.bsky.feed.post/p1": {
                "$type": "app.bsky.feed.post",
                "text": "hi",
                "langs": ["en"],
                "createdAt": CREATED_AT,
            },
            "app.bsky.feed.like/l1": like(),
            "app.bsky.feed.repost/r1": {
                "$type": "app.bsky.feed.repost",
                "subject": SUBJECT,
                "createdAt": CREATED_AT,
            },
            "app.bsky.graph.follow/f1": {
                "$type": "app.bsky.graph.follow",
                "subject": "did:plc:other",
                "createdAt": CREATED_AT,
            },
        }
    )

    rows = decode(DID, car, INGESTED_AT)

    assert {record_type: len(rows[record_type]) for record_type in RECORD_TYPES} == {
        POSTS: 1,
        LIKES: 1,
        REPOSTS: 1,
        FOLLOWS: 1,
    }
    post = rows[POSTS][0]
    assert post["uri"] == f"at://{DID}/app.bsky.feed.post/p1"
    assert post["did"] == DID
    assert post["rev"] == REV
    assert post["created_at"] == datetime(2026, 8, 1, 12, tzinfo=UTC)
    assert post["ingested_at"] == INGESTED_AT
    assert post["text"] == "hi"
    assert rows[LIKES][0]["subject_uri"] == SUBJECT["uri"]
    assert rows[REPOSTS][0]["subject_cid"] == SUBJECT["cid"]
    assert rows[FOLLOWS][0]["subject_did"] == "did:plc:other"


def test_decode_stamps_the_record_cid():
    record = like()
    car = flat_car({"app.bsky.feed.like/l1": record})
    data = libipld.encode_dag_cbor(record)
    expected = libipld.encode_cid(b"\x01q\x12 " + hashlib.sha256(data).digest())

    assert decode(DID, car, INGESTED_AT)[LIKES][0]["cid"] == expected


def test_decode_skips_collections_it_does_not_store():
    car = flat_car(
        {
            "app.bsky.actor.profile/self": {"$type": "app.bsky.actor.profile"},
            "app.bsky.graph.verification/v1": {"createdAt": CREATED_AT},
            "app.bsky.feed.like/l1": like(),
        }
    )

    rows = decode(DID, car, INGESTED_AT)

    assert sum(len(type_rows) for type_rows in rows.values()) == 1


def test_decode_returns_every_record_type_for_an_empty_repo():
    builder = CarBuilder()
    car = builder.build(builder.node([]))

    assert decode(DID, car, INGESTED_AT) == {record_type: [] for record_type in RECORD_TYPES}


@pytest.mark.parametrize(
    ("created_at", "kept"),
    [
        ("2026-08-07T23:59:59.999Z", True),
        ("2026-08-08T00:00:00.000Z", False),
        ("2026-08-07T20:00:00-05:00", False),
        ("2023-02-01T00:00:00Z", True),
        ("2022-11-17T00:00:00Z", True),
        ("2022-11-16T23:59:59Z", False),
        ("1970-01-01T00:00:00Z", False),
    ],
)
def test_decode_keeps_only_the_backfill_window(created_at, kept):
    car = flat_car({"app.bsky.feed.like/l1": like(created_at)})

    assert len(decode(DID, car, INGESTED_AT)[LIKES]) == int(kept)


@pytest.mark.parametrize(
    "record",
    [
        like(created_at=None),
        like(created_at="not a date"),
        {"$type": "app.bsky.feed.like", "createdAt": CREATED_AT},
        "junk",
    ],
)
def test_decode_drops_a_record_missing_required_fields(record):
    car = flat_car({"app.bsky.feed.like/l1": record})

    assert decode(DID, car, INGESTED_AT)[LIKES] == []


def test_decode_walks_every_subtree_and_rebuilds_compressed_keys():
    builder = CarBuilder()
    keys = [f"app.bsky.feed.like/{rkey}" for rkey in ("a1", "a2", "b1", "c1", "c2", "d1")]
    cids = {key: builder.add(like()) for key in keys}
    left = builder.node([(keys[0], cids[keys[0]], None), (keys[1], cids[keys[1]], None)])
    middle = builder.node([(keys[3], cids[keys[3]], None), (keys[4], cids[keys[4]], None)])
    root = builder.node(
        [(keys[2], cids[keys[2]], middle), (keys[5], cids[keys[5]], None)],
        left=left,
    )

    rows = decode(DID, builder.build(root), INGESTED_AT)

    assert [row["uri"] for row in rows[LIKES]] == [f"at://{DID}/{key}" for key in keys]


def test_decode_rejects_a_car_for_another_did():
    car = flat_car({"app.bsky.feed.like/l1": like()}, did="did:plc:someone-else")

    with pytest.raises(ValueError, match="someone-else"):
        decode(DID, car, INGESTED_AT)


def test_decode_raises_on_a_missing_record_block():
    builder = CarBuilder()
    missing = b"\x01q\x12 " + hashlib.sha256(b"absent").digest()
    car = builder.build(builder.node([("app.bsky.feed.like/l1", missing, None)]))

    with pytest.raises(ValueError, match="missing block"):
        decode(DID, car, INGESTED_AT)


def test_decode_raises_on_garbage():
    with pytest.raises(Exception):
        decode(DID, b"not a car", INGESTED_AT)
