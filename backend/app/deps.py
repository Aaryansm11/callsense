"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Header

from pipeline.queue import PostgresJobQueue

_queue = PostgresJobQueue()


def get_queue() -> PostgresJobQueue:
    return _queue


def get_role(x_role: str | None = Header(default="director")) -> str:
    """Role switcher stub (auth is out of scope). The dashboard sends X-Role;
    real RBAC would enforce scope here. Kept permissive for the demo."""
    return (x_role or "director").lower()
