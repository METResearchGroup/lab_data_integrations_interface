import csv
import os
import time

from atproto import Client
from atproto_client.exceptions import BadRequestError
from constants import MICROSECONDS_PER_SECOND, SECONDS_PER_HOUR
from dotenv import load_dotenv


def create_client() -> Client:
    load_dotenv()
    client = Client()
    client.login(os.getenv("BLUESKY_HANDLE"), os.getenv("BLUESKY_APP_PASSWORD"))
    return client


def resolve_did(client: Client, handle: str) -> str | None:
    try:
        return client.app.bsky.actor.get_profile({"actor": handle}).did
    except BadRequestError:
        print(f"Profile not found: @{handle}")
        return None


def build_cursor(hours_back: int) -> int:
    seconds_back = hours_back * SECONDS_PER_HOUR
    return int((time.time() - seconds_back) * MICROSECONDS_PER_SECOND)


def write_csv(filename: str, rows: list[dict], fieldnames: list[str]) -> None:
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {filename}")
