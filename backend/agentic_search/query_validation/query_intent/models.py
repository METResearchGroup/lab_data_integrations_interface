"""The structured form of a natural-language query."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from bluesky_ingestion_jetstream.constants import RecordType

# Shared by validation and SQL generation. A longer list, or a pasted sentence
# standing in for a term, makes a more expensive regex without answering more.
MAX_KEYWORDS = 8
MAX_KEYWORD_LENGTH = 80

# The posts column a keyword filter reads.
TEXT_COLUMN = "text"

KeywordMatch = Literal["any", "all"]


class QueryIntent(BaseModel):
    is_nonsense: bool
    record_type: RecordType | None
    columns: list[str] = Field(default_factory=list)
    start_date: date | None
    end_date: date | None
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Terms to match in post text. Empty when the question does not "
            "filter by what a post says."
        ),
    )
    match: KeywordMatch = Field(
        default="any",
        description="any: one term is enough. all: every term must appear.",
    )
    use_whole_word: bool = Field(
        default=True,
        description=(
            "True wraps each term in an ASCII word boundary. False is a "
            "substring match, used for hashtags, mentions, and CJK text."
        ),
    )
    start_date_inferred: SkipJsonSchema[bool] = Field(
        default=False,
        description="True when a missing start was set to 7 days before the end.",
    )
    end_date_inferred: SkipJsonSchema[bool] = Field(
        default=False,
        description="True when a missing end was set to the current UTC date.",
    )

    @field_validator("keywords")
    @classmethod
    def strip_keywords(_cls, keywords: list[str]) -> list[str]:
        return [keyword.strip() for keyword in keywords]
