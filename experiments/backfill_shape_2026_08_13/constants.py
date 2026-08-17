from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).parent
USERS_FILE = EXPERIMENT_ROOT / "users" / "users.json"
LANDING_ZONE_ROOT = EXPERIMENT_ROOT / "landing_zone"

# Flush every N users, regardless of how many rows that turns out to be.
BATCH_SIZE = 5

WEEKS_BACK = 4
DAYS_BACK = WEEKS_BACK * 7

# getProfiles caps at 25 actors per call.
PROFILES_BATCH_SIZE = 25

TARGET_COLLECTIONS = {
    "app.bsky.feed.post": "posts",
    "app.bsky.feed.like": "likes",
    "app.bsky.feed.repost": "reposts",
    "app.bsky.graph.follow": "follows",
}
