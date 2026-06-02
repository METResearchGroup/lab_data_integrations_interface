"""Shared ingestion status type aliases."""

from __future__ import annotations

from typing import Literal

KeywordStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
SyncStatus = Literal["in_progress", "completed"]
