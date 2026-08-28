"""Accepts a natural-language query and mails the results when it finishes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, status

from backend.agentic_search.handle_query import handle_query
from backend.auth import current_user_email

router = APIRouter()


@router.post("/query", status_code=status.HTTP_202_ACCEPTED)
def query(
    tasks: BackgroundTasks,
    query: str = Body(..., embed=False),
    email: str = Depends(current_user_email),
):
    """Acknowledge the query; the outcome is mailed when it finishes."""

    tasks.add_task(handle_query, query, email)
    return {"status": "accepted"}
