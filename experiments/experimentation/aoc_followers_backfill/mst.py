from atproto import CAR
from atproto_core.cid import CID


def _to_cid(value: bytes | CID | None) -> CID | None:
    if value is None:
        return None
    if isinstance(value, CID):
        return value
    return CID.decode(value)


def _walk_node(blocks: dict, node_cid: CID | None, prev_key: str, records: dict[str, dict]) -> str:
    """Walks one MST node (and its subtrees), reconstructing full keys and
    collecting (key -> record) pairs into `records`. Returns the last full
    key seen, so the caller can keep accumulating prefixes across siblings.
    """
    if node_cid is None:
        return prev_key

    node = blocks[node_cid]
    prev_key = _walk_node(blocks, _to_cid(node["l"]), prev_key, records)

    for entry in node["e"]:
        key_suffix = entry["k"].decode("ascii")
        full_key = prev_key[: entry["p"]] + key_suffix

        value_cid = _to_cid(entry["v"])
        record = blocks.get(value_cid)
        if record is not None:
            records[full_key] = record

        prev_key = full_key
        prev_key = _walk_node(blocks, _to_cid(entry.get("t")), prev_key, records)

    return prev_key


def decode_repo(repo_bytes: bytes) -> tuple[str, dict[str, dict]]:
    """Decodes a `com.atproto.sync.getRepo` response.

    Returns (did, records) where `records` maps the full at-URI of each
    record to its decoded content dict.
    """
    car = CAR.from_bytes(repo_bytes)
    commit = car.blocks[car.root]
    did = commit["did"]

    mst_root_cid = _to_cid(commit["data"])
    keyed_records: dict[str, dict] = {}
    _walk_node(car.blocks, mst_root_cid, "", keyed_records)

    records = {f"at://{did}/{key}": record for key, record in keyed_records.items()}
    return did, records
