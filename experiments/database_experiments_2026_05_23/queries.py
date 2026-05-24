"""Engine-agnostic logical query definitions for the database benchmark.

Run from repo root with PYTHONPATH=.
"""

from dataclasses import dataclass
from enum import StrEnum


class QueryCategory(StrEnum):
    OLAP = "OLAP"
    OLTP = "OLTP"


class QueryId(StrEnum):
    POSTS_TODAY_LIMIT_100 = "posts_today_limit_100"
    TOP_100_POSTERS_PAST_WEEK = "top_100_posters_past_week"
    TRUMP_POST_COUNT_PAST_WEEK = "trump_post_count_past_week"
    POSTS_PER_DAY_PAST_3_WEEKS = "posts_per_day_past_3_weeks"
    LAST_10_POSTS_BY_AUTHOR = "last_10_posts_by_author"
    LAST_10_LIKED_POSTS_BY_AUTHOR = "last_10_liked_posts_by_author"


@dataclass(frozen=True)
class QuerySpec:
    query_id: QueryId
    category: QueryCategory
    description: str
    requires_author_id: bool = False


QUERY_SPECS: list[QuerySpec] = [
    QuerySpec(
        QueryId.POSTS_TODAY_LIMIT_100,
        QueryCategory.OLAP,
        "100 posts from today, timestamp filter + LIMIT 100",
    ),
    QuerySpec(
        QueryId.TOP_100_POSTERS_PAST_WEEK,
        QueryCategory.OLAP,
        "Top 100 users who posted most in past week",
    ),
    QuerySpec(
        QueryId.TRUMP_POST_COUNT_PAST_WEEK,
        QueryCategory.OLAP,
        "Count posts containing word 'Trump' in past week",
    ),
    QuerySpec(
        QueryId.POSTS_PER_DAY_PAST_3_WEEKS,
        QueryCategory.OLAP,
        "Posts per day for past 3 weeks",
    ),
    QuerySpec(
        QueryId.LAST_10_POSTS_BY_AUTHOR,
        QueryCategory.OLTP,
        "Last 10 posts by given author_id",
        requires_author_id=True,
    ),
    QuerySpec(
        QueryId.LAST_10_LIKED_POSTS_BY_AUTHOR,
        QueryCategory.OLTP,
        "Last 10 posts liked by given author_id",
        requires_author_id=True,
    ),
]

QUERY_SPECS_BY_ID: dict[QueryId, QuerySpec] = {spec.query_id: spec for spec in QUERY_SPECS}
