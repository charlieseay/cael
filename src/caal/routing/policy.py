"""Shared routing policy for Sonique + lab agents.

This module centralizes tier order and failover/capacity semantics so CAAL,
Helmsman, and other local processes can consume one contract.
"""

from __future__ import annotations

from typing import Any

CAPACITY_ERROR_HINTS: tuple[str, ...] = (
    "429",
    "rate limit",
    "too many requests",
    "quota",
    "exhaust",
    "insufficient",
    "credit",
    "billing",
    "capacity",
    "overloaded",
)


def is_capacity_error_text(err_text: str) -> bool:
    """True when text looks like quota/rate/capacity exhaustion."""
    s = (err_text or "").lower()
    return any(h in s for h in CAPACITY_ERROR_HINTS)


def is_capacity_error(err: Exception) -> bool:
    """True when an exception indicates quota/rate/capacity exhaustion."""
    return is_capacity_error_text(str(err))


def policy_from_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Build a serializable routing policy snapshot from runtime settings."""
    return {
        "name": "seaynic-shared-routing-policy",
        "version": "2026-04-28",
        "tiers": [
            {
                "tier": 0,
                "label": "simple",
                "provider": settings.get("router_simple_provider", "ollama"),
                "model": settings.get("router_simple_model", "qwen3:4b"),
            },
            {
                "tier": 1,
                "label": "medium",
                "provider": settings.get("router_medium_provider", "openai_compatible"),
                "model": settings.get("router_medium_model", "meta/llama-3.3-70b-instruct"),
            },
            {
                "tier": 2,
                "label": "complex",
                "provider": settings.get("router_complex_provider", "claude_cli"),
                "model": settings.get("router_complex_model", "claude-haiku-4-5"),
            },
        ],
        "failover": {
            "trigger": "capacity|rate|quota exhaustion",
            "strategy": "immediate escalate to next tier in same turn",
            "capacity_error_hints": list(CAPACITY_ERROR_HINTS),
        },
    }
