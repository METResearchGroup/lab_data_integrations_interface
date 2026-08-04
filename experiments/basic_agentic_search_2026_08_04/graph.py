"""LangGraph workflow for basic agentic search.

Flow (from whiteboard):
  Ingest query -> Is this query valid? -> Create the SQL -> Run the query
  -> how to return the query
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class GraphState(TypedDict, total=False):
    """Shared state passed between nodes."""

    query: str
    is_valid: bool
    validation_error: str | None
    sql: str | None
    query_result: Any
    response: str | None


def ingest_query(state: GraphState) -> GraphState:
    """Normalize / accept the inbound natural-language query."""
    query = (state.get("query") or "").strip()
    return {"query": query}


def is_query_valid(state: GraphState) -> GraphState:
    """Decide whether the ingested query is valid to proceed."""
    query = state.get("query") or ""
    if not query:
        return {
            "is_valid": False,
            "validation_error": "Query is empty.",
        }
    return {"is_valid": True, "validation_error": None}


def route_after_validation(state: GraphState) -> Literal["create_the_sql", "__end__"]:
    """Branch after validation: continue or stop."""
    if state.get("is_valid"):
        return "create_the_sql"
    return END


def create_the_sql(state: GraphState) -> GraphState:
    """Translate the validated query into SQL."""
    # Placeholder — wire up LLM / SQL generation here.
    query = state.get("query") or ""
    return {"sql": f"-- TODO: generate SQL for: {query}"}


def run_the_query(state: GraphState) -> GraphState:
    """Execute the generated SQL against the target database."""
    # Placeholder — wire up DuckDB / Postgres / etc. here.
    sql = state.get("sql")
    return {"query_result": {"sql": sql, "rows": []}}


def how_to_return_the_query(state: GraphState) -> GraphState:
    """Format query results into the response returned to the caller."""
    result = state.get("query_result")
    return {"response": str(result)}


def build_graph() -> StateGraph:
    """Assemble the agentic search StateGraph (uncompiled)."""
    workflow = StateGraph(GraphState)

    workflow.add_node("ingest_query", ingest_query)
    workflow.add_node("is_query_valid", is_query_valid)
    workflow.add_node("create_the_sql", create_the_sql)
    workflow.add_node("run_the_query", run_the_query)
    workflow.add_node("how_to_return_the_query", how_to_return_the_query)

    workflow.add_edge(START, "ingest_query")
    workflow.add_edge("ingest_query", "is_query_valid")
    workflow.add_conditional_edges(
        "is_query_valid",
        route_after_validation,
        {
            "create_the_sql": "create_the_sql",
            END: END,
        },
    )
    workflow.add_edge("create_the_sql", "run_the_query")
    workflow.add_edge("run_the_query", "how_to_return_the_query")
    workflow.add_edge("how_to_return_the_query", END)

    return workflow


def compile_graph():
    """Compile the agentic search graph into a runnable app."""
    return build_graph().compile()


graph = compile_graph()


if __name__ == "__main__":
    result = graph.invoke({"query": "How many posts last week?"})
    print(result)
