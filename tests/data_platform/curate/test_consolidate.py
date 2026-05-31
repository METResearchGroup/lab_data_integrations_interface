from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.curate.consolidate import ConsolidateConfig, build_wide_table


def _write_posts(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "uri": "at://a/post/1",
                "url": "https://bsky.app/profile/a/post/1",
                "author_handle": "a.bsky.social",
                "text": "post one",
                "created_at": "2026-01-01T00:00:00Z",
                "like_count": 0,
                "repost_count": 0,
                "reply_count": 0,
                "quote_count": 0,
            },
            {
                "uri": "at://b/post/2",
                "url": "https://bsky.app/profile/b/post/2",
                "author_handle": "b.bsky.social",
                "text": "post two",
                "created_at": "2026-01-02T00:00:00Z",
                "like_count": 1,
                "repost_count": 0,
                "reply_count": 0,
                "quote_count": 0,
            },
        ]
    ).to_csv(path, index=False)


def test_build_wide_table_joins_features(tmp_path: Path) -> None:
    posts_csv = tmp_path / "posts.csv"
    _write_posts(posts_csv)

    features_root = tmp_path / "features"
    features_root.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "uri": "at://a/post/1",
                "label_timestamp": "2026_01_01-00:00:00",
                "is_political": True,
            },
            {
                "uri": "at://b/post/2",
                "label_timestamp": "2026_01_01-00:00:00",
                "is_political": False,
            },
        ]
    ).to_csv(features_root / "is_political.csv", index=False)
    pd.DataFrame(
        [
            {"uri": "at://a/post/1", "label_timestamp": "2026_01_01-00:00:00", "category": "news"},
            {
                "uri": "at://b/post/2",
                "label_timestamp": "2026_01_01-00:00:00",
                "category": "opinion",
            },
        ]
    ).to_csv(features_root / "is_news_or_opinion.csv", index=False)

    wide = build_wide_table(
        ConsolidateConfig(
            posts_csv=posts_csv,
            features_root=features_root,
            feature_names=("is_political", "is_news_or_opinion"),
        )
    )

    assert len(wide) == 2
    assert "news_or_opinion_category" in wide.columns
    assert wide.loc[wide["uri"] == "at://a/post/1", "news_or_opinion_category"].iloc[0] == "news"
    assert wide.loc[wide["uri"] == "at://a/post/1", "is_political"].iloc[0] in {
        True,
        "True",
    }
