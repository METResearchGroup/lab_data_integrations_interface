"""Runs the LangGraph app: validate, generate SQL, execute on Athena."""

from __future__ import annotations

from backend.agentic_search.aws.athena import Athena
from backend.agentic_search.aws.s3 import S3
from backend.agentic_search.graph.graph import build_graph
from backend.agentic_search.graph.state import SearchState
from backend.agentic_search.query_execution.models import ExecutedQuery
from backend.agentic_search.query_validation.models import ValidationResult


def run_langgraph(query: str) -> tuple[ValidationResult, ExecutedQuery | None]:
    """`executed` is None when validation rejected the query."""

    state = build_graph(Athena(), S3()).invoke(SearchState(query=query))
    return state["validation"], state["executed"]
