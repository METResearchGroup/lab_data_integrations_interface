"""What execution hands back."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutedQuery:
    execution_id: str
    # Presigned link to Athena's own result file, which is always CSV.
    result_url: str
