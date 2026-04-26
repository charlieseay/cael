"""Model router — always-on, adaptive routing to the right LLM provider.

Three complexity tiers mapped to configurable providers. The router is ALWAYS
active — there is no enable/disable gate. If all tiers point to the same model
it is a no-op (same provider returned). The key behaviors:

1. Complexity scoring  — regex + heuristics classify each message as SIMPLE /
   MEDIUM / COMPLEX and pick the corresponding provider tier.

2. Adaptive latency    — rolling latency stats per tier. If a tier is
   consistently slow (> SLOW_THRESHOLD_MS average TTFT), the router
   temporarily escalates to the next tier. It de-escalates back after
   RECOVERY_CALLS consecutive fast responses.

3. Ollama health gate  — before routing to any ollama tier, the router does a
   cheap health check. If Ollama is unreachable it skips all local tiers and
   routes straight to the cloud/complex tier.

4. Failure fallback    — a provider that raises during chat() is marked
   unhealthy for FAILURE_COOLDOWN_S seconds, then retried.

The system runs lean by default: prefer the smallest capable model, escalate
only when forced by latency or complexity, de-escalate as soon as conditions
improve.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .providers import LLMProvider

logger = logging.getLogger(__name__)

# ── Complexity tiers ──────────────────────────────────────────────────────────
SIMPLE = 0   # single-action home/device command → small local model
MEDIUM = 1   # multi-step, conditional, multiple devices → medium local model
COMPLEX = 2  # reasoning, explanation, open-ended → cloud / large model

# ── Tuning constants ──────────────────────────────────────────────────────────
SLOW_THRESHOLD_MS = 3_500   # avg TTFT above this → escalate tier
FAST_THRESHOLD_MS = 1_800   # avg TTFT below this → safe to de-escalate
STATS_WINDOW = 5            # rolling window size for latency averages
MIN_SAMPLES = 2             # samples needed before acting on stats
RECOVERY_CALLS = 3          # consecutive fast calls before de-escalating
FAILURE_COOLDOWN_S = 120    # seconds to avoid a provider after a hard failure
OLLAMA_HEALTH_TIMEOUT = 1.5 # seconds for the Ollama /api/tags ping


# ── Complexity patterns ───────────────────────────────────────────────────────
_COMPLEX_RE = [
    re.compile(p, re.I) for p in [
        r"\bwhy\b",
        r"\bexplain\b",
        r"\banalyze\b",
        r"\bsummar",
        r"\bwrite\b.{0,30}\b(email|message|post|note|report)\b",
        r"\bdraft\b",
        r"\bcreate\b.{0,20}\bdocument\b",
        r"\bwhat.s the difference\b",
        r"\bcompare\b",
        r"\badvise\b",
        r"\bshould i\b",
        r"\bwhat should\b",
        r"\bhow (do|can|would)\b",
        r"\btell me about\b",
    ]
]

_MEDIUM_RE = [
    re.compile(p, re.I) for p in [
        r"\bthen\b",
        r"\bafter (that|you|it)\b",
        r"\bbefore\b.{0,20}\b(you|it|that)\b",
        r"\band also\b",
        r"\bas well as\b",
        r"\bif.{0,40}then\b",
        r"\ball (the )?(lights|doors|cameras|devices|blinds)\b",
        r"\beveryone\b",
        r"\bnobody\b",
        r"\bno one\b",
        r"\bwhen (i|we|it|they)\b",
    ]
]

_DEVICE_KW = [
    "light", "door", "camera", "lock", "thermostat",
    "fan", "blind", "curtain", "switch", "plug", "sensor",
]


def score_complexity(message: str) -> int:
    """Score a user message as SIMPLE (0), MEDIUM (1), or COMPLEX (2)."""
    for pat in _COMPLEX_RE:
        if pat.search(message):
            return COMPLEX
    for pat in _MEDIUM_RE:
        if pat.search(message):
            return MEDIUM
    lower = message.lower()
    if sum(1 for kw in _DEVICE_KW if kw in lower) >= 2:
        return MEDIUM
    return SIMPLE


# ── Stats tracker ─────────────────────────────────────────────────────────────

class RouterStats:
    """Rolling latency stats and failure state per tier.

    Thread-safe enough for asyncio (single-threaded event loop).
    """

    def __init__(self) -> None:
        self._samples: dict[int, deque[float]] = {
            t: deque(maxlen=STATS_WINDOW) for t in (SIMPLE, MEDIUM, COMPLEX)
        }
        self._fail_until: dict[int, float] = {}   # tier -> timestamp
        self._consecutive_fast: dict[int, int] = {t: 0 for t in (SIMPLE, MEDIUM, COMPLEX)}
        self._escalated: dict[int, int] = {}       # base_tier -> current_tier

    def record(self, tier: int, latency_ms: float, success: bool = True) -> None:
        """Record a call result. Call this after every LLM response."""
        if not success:
            self._fail_until[tier] = time.time() + FAILURE_COOLDOWN_S
            self._consecutive_fast[tier] = 0
            logger.warning(f"ModelRouter: tier {tier} marked failed for {FAILURE_COOLDOWN_S}s")
            return

        self._samples[tier].append(latency_ms)

        # Count consecutive fast individual calls (not rolling avg) so the
        # recovery counter climbs immediately as latency improves.
        if latency_ms < FAST_THRESHOLD_MS:
            self._consecutive_fast[tier] = self._consecutive_fast.get(tier, 0) + 1
        else:
            self._consecutive_fast[tier] = 0

    def is_failed(self, tier: int) -> bool:
        return time.time() < self._fail_until.get(tier, 0)

    def is_slow(self, tier: int) -> bool:
        avg = self._avg(tier)
        return avg is not None and avg > SLOW_THRESHOLD_MS

    def is_recovered(self, tier: int) -> bool:
        """True when we've seen RECOVERY_CALLS consecutive fast responses.

        Does not require the rolling average to drop — old slow samples in
        the window would otherwise prevent de-escalation too long.
        """
        return self._consecutive_fast.get(tier, 0) >= RECOVERY_CALLS

    def _avg(self, tier: int) -> float | None:
        samples = self._samples[tier]
        if len(samples) < MIN_SAMPLES:
            return None
        return sum(samples) / len(samples)

    def summary(self) -> str:
        parts = []
        labels = {SIMPLE: "simple", MEDIUM: "medium", COMPLEX: "complex"}
        for t, label in labels.items():
            avg = self._avg(t)
            failed = self.is_failed(t)
            status = "FAIL" if failed else (f"{avg:.0f}ms" if avg else "?")
            parts.append(f"{label}={status}")
        return " ".join(parts)


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class RouterConfig:
    # Simple tier — fast local model for single-action commands
    simple_provider: str = "ollama"
    simple_model: str = "qwen3:4b"
    # Medium tier — local model for multi-step reasoning
    medium_provider: str = "ollama"
    medium_model: str = "qwen3:8b"
    # Complex tier — cloud / large model for open-ended reasoning
    complex_provider: str = "claude_cli"
    complex_model: str = "claude-haiku-4-5"
    # Shared ollama settings
    ollama_host: str = "http://localhost:11434"
    think: bool = False
    temperature: float = 0.15
    num_ctx: int = 8192


# ── Health check ──────────────────────────────────────────────────────────────

_ollama_healthy: bool | None = None       # None = unknown
_ollama_checked_at: float = 0.0
_OLLAMA_CHECK_INTERVAL = 30.0             # recheck every 30 s


async def _check_ollama(host: str) -> bool:
    """Ping Ollama's /api/tags. Fast, no model loading. Cached 30 s."""
    global _ollama_healthy, _ollama_checked_at

    now = time.time()
    if _ollama_healthy is not None and now - _ollama_checked_at < _OLLAMA_CHECK_INTERVAL:
        return _ollama_healthy

    try:
        import httpx
        async with httpx.AsyncClient(timeout=OLLAMA_HEALTH_TIMEOUT) as c:
            r = await c.get(f"{host.rstrip('/')}/api/tags")
            _ollama_healthy = r.status_code == 200
    except Exception:
        _ollama_healthy = False

    _ollama_checked_at = now
    if not _ollama_healthy:
        logger.warning("ModelRouter: Ollama unreachable — routing to cloud tier")
    return _ollama_healthy


# ── Router ────────────────────────────────────────────────────────────────────

class ModelRouter:
    """Routes each request to the right LLMProvider.

    Always active — no enable flag. Adapts based on observed latency and
    provider health. Prefers local/cheap models; escalates only when needed.
    """

    def __init__(self, config: RouterConfig) -> None:
        self._config = config
        self._providers: dict[int, LLMProvider] = {}
        self.stats = RouterStats()

    @property
    def config(self) -> RouterConfig:
        return self._config

    def _make_provider(self, tier: int) -> LLMProvider:
        from .providers import create_provider

        if tier == SIMPLE:
            name, model = self._config.simple_provider, self._config.simple_model
        elif tier == MEDIUM:
            name, model = self._config.medium_provider, self._config.medium_model
        else:
            name, model = self._config.complex_provider, self._config.complex_model

        kwargs: dict[str, Any] = {"model": model, "temperature": self._config.temperature}
        if name == "ollama":
            kwargs["base_url"] = self._config.ollama_host
            kwargs["think"] = self._config.think
            kwargs["num_ctx"] = self._config.num_ctx

        labels = {SIMPLE: "simple", MEDIUM: "medium", COMPLEX: "complex"}
        logger.debug(f"ModelRouter: creating {name}/{model} for {labels[tier]} tier")
        return create_provider(name, **kwargs)

    def _provider_for(self, tier: int) -> LLMProvider:
        if tier not in self._providers:
            self._providers[tier] = self._make_provider(tier)
        return self._providers[tier]

    async def route(self, message: str, default_provider: LLMProvider) -> tuple[LLMProvider, int]:
        """Return (provider, tier) for this message.

        Complexity scoring picks the base tier. Adaptive logic may escalate
        it based on latency stats or Ollama health.
        """
        base_tier = score_complexity(message)
        tier = base_tier

        # Check Ollama health once before trying any local tier
        ollama_ok = True
        is_local_tier = (
            self._config.simple_provider == "ollama" or
            self._config.medium_provider == "ollama"
        )
        if is_local_tier and tier < COMPLEX:
            ollama_ok = await _check_ollama(self._config.ollama_host)
            if not ollama_ok:
                tier = COMPLEX

        # Escalate if the target tier is slow or failed
        while tier < COMPLEX and (self.stats.is_slow(tier) or self.stats.is_failed(tier)):
            tier += 1
            logger.info(f"ModelRouter: escalating to tier {tier} "
                        f"(slow={self.stats.is_slow(tier-1)}, "
                        f"failed={self.stats.is_failed(tier-1)})")

        # De-escalate if a lower tier has recovered
        if tier > base_tier:
            for candidate in range(base_tier, tier):
                if self.stats.is_recovered(candidate):
                    tier = candidate
                    logger.info(f"ModelRouter: de-escalating to tier {tier} (recovered)")
                    break

        labels = {SIMPLE: "simple", MEDIUM: "medium", COMPLEX: "complex"}
        logger.info(
            f"ModelRouter: {labels[base_tier]}→{labels[tier]} "
            f"({message[:50]!r}) | {self.stats.summary()}"
        )

        return self._provider_for(tier), tier

    def record(self, tier: int, latency_ms: float, success: bool = True) -> None:
        """Feed a call result back to the stats tracker."""
        self.stats.record(tier, latency_ms, success)


def create_router_from_settings(settings: dict[str, Any]) -> ModelRouter:
    """Build a ModelRouter from CAAL settings. Always returns a router."""
    return ModelRouter(RouterConfig(
        simple_provider=settings.get("router_simple_provider", "ollama"),
        simple_model=settings.get("router_simple_model", "qwen3:4b"),
        medium_provider=settings.get("router_medium_provider", "ollama"),
        medium_model=settings.get("router_medium_model", "qwen3:8b"),
        complex_provider=settings.get("router_complex_provider", "claude_cli"),
        complex_model=settings.get("router_complex_model", "claude-haiku-4-5"),
        ollama_host=settings.get("ollama_host", "http://localhost:11434"),
        think=settings.get("think", False),
        temperature=settings.get("temperature", 0.15),
        num_ctx=settings.get("num_ctx", 8192),
    ))
