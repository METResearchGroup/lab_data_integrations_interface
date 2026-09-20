"""Adapters between the graph's state and the functions that do the work."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END
from pyiceberg.catalog import Catalog

from backend.agentic_search.graph.state import SearchState
from backend.agentic_search.query_execution.execute import execute_query
from backend.agentic_search.query_generation.generate import generate_sql
from backend.agentic_search.query_postprocessing.check_scan_cost import reason_over_scan_limit
from backend.agentic_search.query_postprocessing.check_select_only import is_select_only
from backend.agentic_search.query_validation.orchestrator import validate_query
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE
from lib.aws.athena import Athena
from lib.aws.s3 import S3

# Nodes return only the fields they set; langgraph merges them onto the state.
StateUpdate = dict[str, Any]


def validate_node(state: SearchState) -> StateUpdate:
    return {"validation": validate_query(state.query)}


def generate_node(state: SearchState) -> StateUpdate:
    assert state.validation is not None  # our routing guarantees this
    return {"generated": generate_sql(state.validation.intent)}


def postprocess_node(state: SearchState, *, catalog: Catalog) -> StateUpdate:
    assert state.validation is not None
    assert state.generated is not None

    if not is_select_only(state.generated.sql):
        return {"rejection": "only SELECT queries are allowed"}

    table = catalog.load_table((GLUE_DATABASE, state.generated.record_type))
    return {"rejection": reason_over_scan_limit(table, state.validation.intent)}


def execute_node(state: SearchState, *, athena: Athena, s3: S3) -> StateUpdate:
    assert state.generated is not None
    return {"executed": execute_query(state.generated, athena=athena, s3=s3)}


def route_after_validation(state: SearchState) -> str:
    """An invalid query stops here instead of reaching Athena."""

    assert state.validation is not None
    return "generate" if state.validation.valid else END


def route_after_postprocessing(state: SearchState) -> str:
    return "execute" if state.rejection is None else END
