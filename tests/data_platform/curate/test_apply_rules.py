from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data_platform.curate.apply_rules import (
    CurateRulesConfig,
    FilterRule,
    OutputConfig,
    apply_rules,
    load_rules_config,
)


def _mirrorview_rules() -> CurateRulesConfig:
    return CurateRulesConfig(
        name="mirrorview",
        output=OutputConfig(filename="mirrorview.csv"),
        filters=[
            FilterRule(column="news_or_opinion_category", op="eq", value="news"),
            FilterRule(column="is_political", op="eq", value=True),
            FilterRule(column="is_self_contained", op="eq", value=True),
            FilterRule(
                column="is_structurally_complete", op="eq", value=True
            ),
        ],
    )


def test_apply_rules_mirrorview_filters() -> None:
    df = pd.DataFrame(
        [
            {
                "uri": "1",
                "news_or_opinion_category": "news",
                "is_political": "True",
                "is_self_contained": "True",
                "is_structurally_complete": "True",
            },
            {
                "uri": "2",
                "news_or_opinion_category": "opinion",
                "is_political": "True",
                "is_self_contained": "True",
                "is_structurally_complete": "True",
            },
            {
                "uri": "3",
                "news_or_opinion_category": "news",
                "is_political": "False",
                "is_self_contained": "True",
                "is_structurally_complete": "True",
            },
            {
                "uri": "4",
                "news_or_opinion_category": "news",
                "is_political": "True",
                "is_self_contained": "False",
                "is_structurally_complete": "True",
            },
        ]
    )
    result = apply_rules(df, _mirrorview_rules())
    assert len(result.dataframe) == 1
    assert result.dataframe.iloc[0]["uri"] == "1"
    assert len(result.steps) == 4
    assert result.steps[0].records_before == 4
    assert result.steps[0].records_passing == 3
    assert result.steps[-1].records_passing == 1


def test_load_rules_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "mirrorview.yaml"
    config_path.write_text(
        """
name: mirrorview
output:
  filename: mirrorview.csv
filters:
  - column: news_or_opinion_category
    op: eq
    value: news
""",
        encoding="utf-8",
    )
    rules = load_rules_config(config_path)
    assert rules.name == "mirrorview"
    assert rules.output.filename == "mirrorview.csv"
    assert len(rules.filters) == 1


def test_apply_rules_missing_column_raises() -> None:
    df = pd.DataFrame([{"uri": "1"}])
    with pytest.raises(KeyError, match="missing_col"):
        apply_rules(
            df,
            CurateRulesConfig(
                name="test",
                filters=[FilterRule(column="missing_col", op="eq", value="x")],
            ),
        )
