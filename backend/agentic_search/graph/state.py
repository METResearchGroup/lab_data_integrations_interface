"""What flows between the graph's nodes."""

from __future__ import annotations

from dataclasses import dataclass

from backend.agentic_search.query_execution.models import ExecutedQuery
from backend.agentic_search.query_generation.models import GeneratedQuery
from backend.agentic_search.query_validation.models import ValidationResult


@dataclass
class SearchState:
    # Every field past `query` is filled in by the node that produces it
    # An invalid query ends with `generated` and `executed` still None.
    query: str
    validation: ValidationResult | None = None
    generated: GeneratedQuery | None = None
    executed: ExecutedQuery | None = None
