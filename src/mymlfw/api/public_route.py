"""``@public_route`` contract: routes that skip ``get_project_db``.

Project-scoped handlers must inject ``Depends(get_project_db)``. Mark only
health, auth, and similar endpoints with ``@public_route``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

F = TypeVar("F", bound=Callable[..., object])

PUBLIC_ROUTE_ATTR = "__mymlfw_public_route__"


def public_route(fn: F) -> F:
    """Mark a FastAPI endpoint as not requiring ``ProjectScopedDB``."""
    setattr(fn, PUBLIC_ROUTE_ATTR, True)
    return fn


def is_public_route(fn: Callable[..., object]) -> bool:
    return bool(getattr(fn, PUBLIC_ROUTE_ATTR, False))
