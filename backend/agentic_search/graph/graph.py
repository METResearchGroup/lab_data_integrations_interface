"""Wires the three search stages together. Order lives here and nowhere else."""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from backend.agentic_search.graph.nodes import (
    execute_node,
    generate_node,
    route_after_validation,
    validate_node,
)
from backend.agentic_search.graph.state import SearchState
from lib.aws.athena import Athena
from lib.aws.s3 import S3


def build_graph(athena: Athena, s3: S3):
    builder = StateGraph(SearchState)

    builder.add_node("validate", validate_node)
    builder.add_node("generate", generate_node)
    builder.add_node("execute", partial(execute_node, athena=athena, s3=s3))

    builder.add_edge(START, "validate")
    builder.add_conditional_edges("validate", route_after_validation, ["generate", END])
    builder.add_edge("generate", "execute")
    builder.add_edge("execute", END)

    return builder.compile()
