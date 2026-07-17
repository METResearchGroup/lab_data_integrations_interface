import time
from datetime import UTC, datetime

from atproto import Client

from experimentation.aoc_followers_backfill.client import create_public_client, create_relay_client
from experimentation.aoc_followers_backfill.constants import TIMING_SCALES
from experimentation.aoc_followers_backfill.discovery import get_follower_dids
from experimentation.aoc_followers_backfill.timing_output import write_timing_outputs


def _is_rate_limited(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code == 429:
        return True
    message = str(exc).lower()
    return "429" in message or "ratelimit" in message


def _time_get_repo(relay_client: Client, did: str) -> tuple[float, int | None, str | None, bool]:
    start = time.perf_counter()
    try:
        repo_bytes = relay_client.com.atproto.sync.get_repo({"did": did})
    except Exception as e:
        duration = time.perf_counter() - start
        return duration, None, str(e), _is_rate_limited(e)
    duration = time.perf_counter() - start
    return duration, len(repo_bytes), None, False


def main() -> None:
    run_start = datetime.now(UTC)

    client = create_public_client()
    relay_client = create_relay_client()

    max_scale = max(TIMING_SCALES)
    users, target_did = get_follower_dids(client, max_scale)

    calls: list[dict] = []
    for i, user in enumerate(users, start=1):
        duration, size, error, rate_limited = _time_get_repo(relay_client, user["did"])
        calls.append(
            {
                "handle": user["handle"],
                "did": user["did"],
                "duration_seconds": duration,
                "repo_size_bytes": size,
                "error": error,
                "rate_limited": rate_limited,
            }
        )
        status = f"error: {error}" if error else f"{size} bytes"
        print(f"[{i}/{len(users)}] {user['handle']} - {duration:.3f}s - {status}")

    output_dir = write_timing_outputs(target_did=target_did, calls=calls, run_start=run_start)
    print(f"Wrote timing output to {output_dir}")

    for n in sorted(TIMING_SCALES):
        tier_calls = calls[:n]
        if len(tier_calls) < n:
            continue
        durations = [c["duration_seconds"] for c in tier_calls]
        errors = sum(1 for c in tier_calls if c["error"] is not None)
        print(
            f"n={n:>5}  total={sum(durations):>8.2f}s  "
            f"mean={sum(durations) / len(durations):>6.3f}s  "
            f"errors={errors}  "
            f"rate_limited={sum(1 for c in tier_calls if c['rate_limited'])}"
        )


if __name__ == "__main__":
    main()
