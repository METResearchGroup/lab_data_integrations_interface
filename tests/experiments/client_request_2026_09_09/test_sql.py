"""Tests for build_unload_sql() and escape_sql_literal()."""

import re
from datetime import date

from experiments.client_request_2026_09_09.sql import build_unload_sql, escape_sql_literal
from tests.experiments.client_request_2026_09_09.conftest import candidate_by_id

RUN_DATE = date(2026, 9, 9)
UNLOAD_S3_URI = (
    "s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/"
    "2026_09_09-12:00:00/unload/cooper/"
)
LIKE_NEEDLE_PATTERN = re.compile(r"LIKE '%' \|\| '([^']*)' \|\| '%'")
CASE_WHEN_PATTERN = re.compile(
    r"WHEN LOWER\(text\) LIKE '%' \|\| '([^']*)' \|\| '%' THEN '([^']*)'"
)
SMOKE_LIMIT = 100


def _build(candidate_id: str, smoke_limit: int | None = None) -> str:
    return build_unload_sql(
        candidate_by_id(candidate_id),
        run_date=RUN_DATE,
        s3_uri=UNLOAD_S3_URI,
        smoke_limit=smoke_limit,
    )


def _like_needles(sql: str) -> list[str]:
    return LIKE_NEEDLE_PATTERN.findall(sql)


def _unique_like_needles(sql: str) -> list[str]:
    return list(dict.fromkeys(_like_needles(sql)))


class TestEscapeSqlLiteral:
    """Tests for escape_sql_literal()."""

    def test_doubles_single_quotes(self):
        """A single quote in a name string is doubled for SQL literals."""
        # Arrange
        value = "O'Brien"
        expected = "O''Brien"

        # Act
        result = escape_sql_literal(value)

        # Assert
        assert result == expected


class TestBuildUnloadSql:
    """Tests for build_unload_sql()."""

    def test_cooper_window_starts_on_coverage_floor(self):
        """Cooper's WHERE clause starts on 2026-08-01 and ends after run_date."""
        # Arrange
        expected_start = "created_at >= TIMESTAMP '2026-08-01 00:00:00'"
        expected_end = "created_at < TIMESTAMP '2026-09-10 00:00:00'"

        # Act
        result = _build("cooper")

        # Assert
        assert expected_start in result
        assert expected_end in result

    def test_el_sayed_window_starts_on_primary(self):
        """El-Sayed's start timestamp is the Michigan primary."""
        # Arrange
        expected_start = "TIMESTAMP '2026-08-04 00:00:00'"

        # Act
        result = _build("el_sayed")

        # Assert
        assert f"created_at >= {expected_start}" in result

    def test_cooper_like_patterns_are_roy_cooper_only(self):
        """Cooper LIKE patterns equal roy cooper wrapped in wildcards."""
        # Arrange
        expected = ["roy cooper"]

        # Act
        result = _build("cooper")
        needles = _unique_like_needles(result)

        # Assert
        assert needles == expected
        assert "|| 'cooper' ||" not in result

    def test_el_sayed_like_patterns_include_hyphen_variants(self):
        """El-Sayed inner select matches hyphen, space, and closed forms."""
        # Arrange
        expected_needles = ("el-sayed", "el sayed", "elsayed")

        # Act
        result = _build("el_sayed")
        needles = set(_like_needles(result))

        # Assert
        assert set(expected_needles) <= needles

    def test_becerra_like_patterns_include_misspelling(self):
        """Becerra patterns include the given name plus Beccera misspelling."""
        # Arrange
        expected_needles = {"xavier becerra", "xavier beccera"}

        # Act
        result = _build("becerra")
        needles = set(_like_needles(result))

        # Assert
        assert expected_needles <= needles
        assert "|| 'becerra' ||" not in result

    def test_smoke_limit_appends_limit_100(self):
        """An integer smoke_limit adds LIMIT 100 to the inner select."""
        # Arrange
        expected = "LIMIT 100"

        # Act
        result = _build("cooper", smoke_limit=SMOKE_LIMIT)

        # Assert
        assert expected in result

    def test_none_smoke_limit_omits_limit(self):
        """smoke_limit None means the SQL has no LIMIT."""
        # Arrange / Act
        result = _build("cooper", smoke_limit=None)

        # Assert
        assert "LIMIT" not in result

    def test_unload_wrapper_and_from_posts(self):
        """SQL is UNLOAD of posts to zstd Parquet without a qualified FROM."""
        # Arrange / Act
        result = _build("talarico")

        # Assert
        assert result.startswith("UNLOAD")
        assert "CAST(created_at AS TIMESTAMP)" in result
        assert "format = 'PARQUET'" in result
        assert "compression = 'ZSTD'" in result
        assert "FROM posts" in result
        assert "FROM bluesky_raw.posts" not in result
        assert "created_at_day" not in result
        assert "ORDER BY" not in result

    def test_matched_name_string_case_follows_name_string_order(self):
        """The CASE / WHEN chain lists name_strings in contract order."""
        # Arrange
        candidate = candidate_by_id("el_sayed")
        expected = list(candidate.name_strings)

        # Act
        result = _build("el_sayed")
        when_needles = [match[0] for match in CASE_WHEN_PATTERN.findall(result)]
        then_literals = [match[1] for match in CASE_WHEN_PATTERN.findall(result)]

        # Assert
        assert when_needles == expected
        assert then_literals == expected
