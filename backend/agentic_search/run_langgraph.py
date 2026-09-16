"""Runs the LangGraph app: validate, generate SQL, postprocess, execute on Athena."""

from __future__ import annotations

from backend.agentic_search.graph.graph import build_graph
from backend.agentic_search.graph.state import SearchState
from backend.agentic_search.query_execution.models import ExecutedQuery
from backend.agentic_search.query_validation.models import ValidationResult
from bluesky_ingestion_jetstream.aws.catalog import build_catalog
from lib.aws.athena import Athena
from lib.aws.s3 import S3


def run_langgraph(query: str) -> tuple[ValidationResult, str | None, ExecutedQuery | None]:
    """`executed` is None when validation rejected the query, or `rejection` says why."""

    state = build_graph(Athena(), S3(), build_catalog()).invoke(SearchState(query=query))
    return state["validation"], state["rejection"], state["executed"]
