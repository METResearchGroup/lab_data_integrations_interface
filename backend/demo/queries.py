"""Hardcoded demo queries that skip the pipeline and mail canned sample data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

DELAY_SECONDS = 2


@dataclass(frozen=True)
class DemoQuery:
    text: str
    summary: str
    csv: Path


DEMO_QUERIES = [
    DemoQuery(
        text="Which posts were most liked or reposted in the last week?",
        summary=(
            "50 posts from the last 7 days, ranked by likes + reposts.\n\n"
            "  1. @luzoutside.bsky.social: 19,778 likes, 3,534 reposts\n"
            "  2. @juneinthecity.bsky.social: 21,288 likes, 1,704 reposts\n"
            "  3. @priyaruns.bsky.social: 17,998 likes, 3,260 reposts"
        ),
        csv=DATA_DIR / "most_engaged_posts_last_week.csv",
    ),
    DemoQuery(
        text="Which users have the highest ratio of engagement to followers?",
        summary=(
            "40 users ranked by engagements per follower over the last 30 days.\n\n"
            "  1. @otisdaily.bsky.social: 4.82 per follower (424 followers)\n"
            "  2. @mayamakes.bsky.social: 3.44 per follower (3,830 followers)\n"
            "  3. @miraplays.bsky.social: 2.51 per follower (2,271 followers)\n"
            "  4. @selinpod.bsky.social: 2.15 per follower (5,677 followers)\n"
            "  5. @wesworks.bsky.social: 2.08 per follower (923 followers)"
        ),
        csv=DATA_DIR / "engagement_to_follower_ratio.csv",
    ),
    DemoQuery(
        text=(
            "How are people feeling about the upcoming midterm elections? And what are "
            "some representative posts?"
        ),
        summary=(
            "Sentiment across 30 representative posts from the last 14 days:\n\n"
            "  - Negative: 43%\n"
            "  - Neutral: 33%\n"
            "  - Positive: 23%\n\n"
            "Most common themes: turnout, election integrity, cost of living, "
            "polarization, local races."
        ),
        csv=DATA_DIR / "midterm_sentiment_representative_posts.csv",
    ),
]


def _normalize(query: str) -> str:
    return " ".join(query.split()).casefold()


_BY_TEXT = {_normalize(demo.text): demo for demo in DEMO_QUERIES}


def match_demo_query(query: str) -> DemoQuery | None:
    return _BY_TEXT.get(_normalize(query))
