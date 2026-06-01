from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import yaml
from pydantic import BaseModel, Field

BOOL_COLUMNS: frozenset[str] = frozenset(
    {"is_political", "is_self_contained", "is_structurally_complete"}
)


class FilterRule(BaseModel):
    column: str
    op: Literal["eq", "in", "ne"]
    value: str | bool | list[str | bool]


class OutputConfig(BaseModel):
    filename: str = "dataset.csv"


class CurateRulesConfig(BaseModel):
    name: str
    output: OutputConfig = Field(default_factory=OutputConfig)
    filters: list[FilterRule] = Field(default_factory=list)


@dataclass(frozen=True)
class FilterStepResult:
    rule: FilterRule
    records_before: int
    records_passing: int


@dataclass(frozen=True)
class ApplyRulesResult:
    dataframe: pd.DataFrame
    steps: list[FilterStepResult]


def load_rules_config(path: Path) -> CurateRulesConfig:
    with path.open(encoding="utf-8") as f:
        raw: Any = yaml.safe_load(f)
    return CurateRulesConfig.model_validate(raw)


def _normalize_bool(series: pd.Series) -> pd.Series:
    def to_bool(value: object) -> bool | object:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return pd.NA
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return pd.NA

    return series.map(to_bool)


def _compare_eq(series: pd.Series, expected: object) -> pd.Series:
    if series.name in BOOL_COLUMNS or isinstance(expected, bool):
        normalized = _normalize_bool(series)
        if isinstance(expected, bool):
            return normalized == expected
        expected_bool = str(expected).strip().lower() in {"true", "1", "yes"}
        return normalized == expected_bool
    return series.astype(str) == str(expected)


def _filter_mask(df: pd.DataFrame, rule: FilterRule) -> pd.Series:
    if rule.column not in df.columns:
        raise KeyError(f"Filter column not found in wide table: {rule.column}")

    series = cast(pd.Series, df[rule.column])
    if rule.op == "eq":
        mask = _compare_eq(series, rule.value)
    elif rule.op == "ne":
        mask = ~_compare_eq(series, rule.value)
    elif rule.op == "in":
        if not isinstance(rule.value, list):
            raise ValueError(f"Filter 'in' requires a list value: {rule.column}")
        mask = pd.Series(False, index=df.index)
        for item in rule.value:
            mask |= _compare_eq(series, item)
    else:
        raise ValueError(f"Unsupported filter op: {rule.op}")

    return mask.fillna(False)


def apply_rules(df: pd.DataFrame, rules: CurateRulesConfig) -> ApplyRulesResult:
    """Apply YAML filters sequentially (AND), recording pass counts per step."""
    result = df
    steps: list[FilterStepResult] = []
    for rule in rules.filters:
        before = len(result)
        mask = _filter_mask(result, rule)
        passing = int(mask.sum())
        result = result.loc[mask].reset_index(drop=True)
        steps.append(
            FilterStepResult(
                rule=rule,
                records_before=before,
                records_passing=passing,
            )
        )
    return ApplyRulesResult(dataframe=result, steps=steps)
