#!/usr/bin/env python3
"""
CAAL Voice Framework - Voice Agent
==================================

A voice assistant with MCP integrations for n8n workflows.

Usage:
    python voice_agent.py dev

Configuration:
    - .env: Environment variables (MCP URL, model settings)
    - prompt/default.md: Agent system prompt

Environment Variables:
    SPEACHES_URL        - Speaches STT service URL (default: "http://speaches:8000")
    KOKORO_URL          - Kokoro TTS service URL (default: "http://kokoro:8880")
    WHISPER_MODEL       - Whisper model for STT (default: "Systran/faster-whisper-small")
    TTS_VOICE           - Kokoro voice name (default: "af_heart")
    OLLAMA_MODEL        - Ollama model name (default: "ministral-3:8b")
    OLLAMA_THINK        - Enable thinking mode (default: "false")
    TIMEZONE            - Timezone for date/time (default: "Pacific Time")
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import time
from urllib.parse import urljoin

import requests

# Add src directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv

# Load environment variables from .env
_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_script_dir, ".env"))

from livekit import agents, rtc  # noqa: E402
from livekit.agents import Agent, AgentSession, mcp  # noqa: E402
from livekit.plugins import groq as groq_plugin  # noqa: E402
from livekit.plugins import openai, silero  # noqa: E402

from caal import CAALLLM  # noqa: E402
from caal.integrations import (  # noqa: E402
    HelmsmanTools,
    iOSBridgeTools,
    LightRAGTools,
    MacControlTools,
    MCPHubTools,
    MemoryTools,
    NetworkTools,
    RouterTools,
    WebSearchTools,
    create_hass_rest_tools,
    create_hass_tools,
    detect_hass_tool_prefix,
    discover_n8n_workflows,
    prepare_lazy_mcp_servers,
    load_mcp_config,
)
from caal.integrations.mcp_loader import LazyMCPServer  # noqa: E402
from caal.deterministic_intents import (  # noqa: E402
    current_time_summary,
    current_model_summary,
    looks_like_model_request,
    looks_like_simple_greeting,
    looks_like_network_status_request,
    looks_like_time_request,
    looks_like_project_list_request,
    network_status_summary,
    simple_greeting_response,
    try_projects_inventory_fallback,
)
from caal.llm import ToolDataCache, llm_node as run_llm_node  # noqa: E402
from caal.memory import ShortTermMemory  # noqa: E402
from caal.stt import WakeWordGatedSTT  # noqa: E402
from caal.tts.sync_openai_tts import SyncOpenAITTS  # noqa: E402
from caal.utils.formatting import strip_markdown_for_tts  # noqa: E402

# Configure logging - LiveKit adds LogQueueHandler to root in worker processes,
# so we use non-propagating loggers with our own handler to avoid duplicates
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(logging.Formatter("%(message)s"))

# voice-agent logger (this file)
logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(_log_handler)

# caal package logger (src/caal/*)
_caal_logger = logging.getLogger("caal")
_caal_logger.setLevel(logging.INFO)
_caal_logger.propagate = False
_caal_logger.addHandler(_log_handler)

# Suppress verbose logs from dependencies
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("groq._base_client").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("livekit").setLevel(logging.WARNING)
logging.getLogger("livekit_api").setLevel(logging.WARNING)
logging.getLogger("livekit.agents.tts").setLevel(logging.ERROR)  # Suppress "no request_id" warnings
logging.getLogger("livekit.agents.voice").setLevel(logging.WARNING)
logging.getLogger("livekit.plugins.openai.tts").setLevel(logging.WARNING)

# Per-process guardrails to avoid overlapping room jobs during reconnect churn.
_ROOM_GUARD_LOCK = asyncio.Lock()
_ACTIVE_ROOMS: set[str] = set()
_DRAINING_ROOMS: set[str] = set()
_ROOM_GUARD_WAIT_SECONDS = 6.0

# =============================================================================
# Configuration
# =============================================================================

# Infrastructure config (from .env only - URLs, tokens, etc.)
SPEACHES_URL = os.getenv("SPEACHES_URL", "http://speaches:8000")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "Systran/faster-whisper-small")
KOKORO_URL = os.getenv("KOKORO_URL", "http://kokoro:8880")
PIPER_URL = os.getenv("PIPER_URL", SPEACHES_URL)  # Separate URL for Piper TTS
TTS_MODEL = os.getenv("TTS_MODEL", "kokoro")
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
logger.info(f"[TTS Config] KOKORO_URL={KOKORO_URL}, PIPER_URL={PIPER_URL}, TTS_MODEL={TTS_MODEL}, TTS_SPEED={TTS_SPEED}")
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() == "true"
TIMEZONE_ID = os.getenv("TIMEZONE", "America/Los_Angeles")
TIMEZONE_DISPLAY = os.getenv("TIMEZONE_DISPLAY", "Pacific Time")
LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://host.docker.internal:8128")

# Import settings module for runtime-configurable values
from caal import settings as settings_module  # noqa: E402


def _is_kokoro_healthy(timeout_s: float = 1.5) -> bool:
    """Fast health probe for Kokoro runtime routing decisions."""
    try:
        health_url = urljoin(KOKORO_URL.rstrip("/") + "/", "health")
        r = requests.get(health_url, timeout=timeout_s)
        return r.status_code == 200
    except Exception:
        return False


def get_wake_greetings(language: str) -> list[str]:
    """Get wake greetings from file for the given language."""
    return settings_module.load_greetings(language)


def get_runtime_settings() -> dict:
    """Get runtime-configurable settings.

    These can be changed via the settings UI without rebuilding.
    Falls back to .env values for backwards compatibility.

    Priority: settings.json (explicit) > .env > DEFAULT_SETTINGS
    """
    settings = settings_module.load_settings()
    user_settings = settings_module.load_user_settings()  # Only explicitly set values

    return {
        # Language
        "language": settings.get("language", "en"),
        # TTS settings
        "tts_provider": user_settings.get("tts_provider") or os.getenv("TTS_PROVIDER", "auto"),
        "tts_voice_kokoro": settings.get("tts_voice_kokoro") or os.getenv("TTS_VOICE", "am_puck"),
        "tts_voice_piper": settings.get("tts_voice_piper") or "speaches-ai/piper-en_US-ryan-high",
        # STT Provider settings
        "stt_provider": user_settings.get("stt_provider") or os.getenv("STT_PROVIDER", "speaches"),
        # LLM Provider settings - .env overrides default, user setting overrides .env
        "llm_provider": user_settings.get("llm_provider") or os.getenv("LLM_PROVIDER", "ollama"),
        "temperature": settings.get("temperature", float(os.getenv("OLLAMA_TEMPERATURE", "0.15"))),
        # Ollama settings
        "ollama_host": (
            user_settings.get("ollama_host")
            or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ),
        "ollama_model": (
            user_settings.get("ollama_model")
            or os.getenv("OLLAMA_MODEL", "ministral-3:8b")
        ),
        "num_ctx": settings.get("num_ctx", int(os.getenv("OLLAMA_NUM_CTX", "8192"))),
        "think": OLLAMA_THINK,  # Only applies to Ollama
        # Groq settings
        "groq_api_key": settings.get("groq_api_key") or os.getenv("GROQ_API_KEY", ""),
        "groq_model": (
            user_settings.get("groq_model")
            or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        ),
        # OpenAI-compatible settings
        "openai_base_url": (
            user_settings.get("openai_base_url")
            or os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
        ),
        "openai_api_key": (
            settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
        ),
        "openai_model": (
            user_settings.get("openai_model")
            or os.getenv("OPENAI_MODEL", "")
        ),
        # OpenRouter settings
        "openrouter_api_key": (
            settings.get("openrouter_api_key")
            or os.getenv("OPENROUTER_API_KEY", "")
        ),
        "openrouter_model": (
            user_settings.get("openrouter_model")
            or os.getenv("OPENROUTER_MODEL", "openai/gpt-4")
        ),
        # CLI provider model settings
        "claude_cli_model": (
            user_settings.get("claude_cli_model")
            or settings.get("claude_cli_model", "claude-haiku-4-5")
        ),
        "cursor_cli_model": (
            user_settings.get("cursor_cli_model")
            or settings.get("cursor_cli_model", "")
        ),
        "gemini_cli_model": (
            user_settings.get("gemini_cli_model")
            or settings.get("gemini_cli_model", "gemini-2.0-flash")
        ),
        # Model router tiers (local -> remote -> complex)
        "router_simple_provider": settings.get("router_simple_provider", "ollama"),
        "router_simple_model": settings.get("router_simple_model", "qwen3:4b"),
        "router_medium_provider": settings.get("router_medium_provider", "ollama"),
        "router_medium_model": settings.get("router_medium_model", "qwen3:8b"),
        "router_complex_provider": settings.get("router_complex_provider", "claude_cli"),
        "router_complex_model": settings.get("router_complex_model", "claude-haiku-4-5"),
        # Shared settings
        "max_turns": settings.get("max_turns", int(os.getenv("OLLAMA_MAX_TURNS", "20"))),
        "tool_cache_size": settings.get("tool_cache_size", int(os.getenv("TOOL_CACHE_SIZE", "3"))),
        # Turn detection settings
        "allow_interruptions": settings.get("allow_interruptions", True),
        "min_endpointing_delay": settings.get("min_endpointing_delay", 0.5),
        "vad_sample_rate": settings.get("vad_sample_rate", 8000),
        "vad_activation_threshold": settings.get("vad_activation_threshold", 0.65),
        "vad_min_silence_duration": settings.get("vad_min_silence_duration", 0.7),
    }


def load_prompt(language: str = "en") -> str:
    """Load and populate prompt template with date context."""
    # Prefer settings.json (set by SoniqueBar) over env var defaults
    settings = settings_module.load_settings()
    tz_id = settings.get("timezone_id") or TIMEZONE_ID
    tz_display = settings.get("timezone_display") or TIMEZONE_DISPLAY
    return settings_module.load_prompt_with_context(
        timezone_id=tz_id,
        timezone_display=tz_display,
        language=language,
    )


# =============================================================================
# Agent Definition
# =============================================================================

def _last_user_utterance_text(chat_ctx) -> str:
    """Best-effort extract of the latest user message from LiveKit chat context."""
    items = getattr(chat_ctx, "items", None) or []
    for item in reversed(list(items)):
        if getattr(item, "role", None) != "user":
            continue
        raw = getattr(item, "text_content", None)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    return ""


# Type alias for tool status callback
ToolStatusCallback = callable  # async (bool, list[str], list[dict]) -> None


class VoiceAssistant(LightRAGTools, MCPHubTools, RouterTools, HelmsmanTools, MacControlTools, NetworkTools, MemoryTools, WebSearchTools, iOSBridgeTools, Agent):
    """Voice assistant with MCP tools, web search, and short-term memory."""

    def __init__(
        self,
        caal_llm: CAALLLM,
        language: str = "en",
        mcp_servers: dict[str, mcp.MCPServerHTTP] | None = None,
        n8n_workflow_tools: list[dict] | None = None,
        n8n_workflow_name_map: dict[str, str] | None = None,
        n8n_base_url: str | None = None,
        on_tool_status: ToolStatusCallback | None = None,
        tool_cache_size: int = 3,
        max_turns: int = 20,
        hass_tool_definitions: list[dict] | None = None,
        hass_tool_callables: dict | None = None,
        short_term_memory: ShortTermMemory | None = None,
        on_ios_calendar_query: callable | None = None,
    ) -> None:
        super().__init__(
            instructions=load_prompt(language=language),
            llm=caal_llm,  # Satisfies LLM interface requirement
        )

        # Store provider for llm_node access
        self._provider = caal_llm.provider_instance

        # All MCP servers (for multi-MCP support)
        # Named _caal_mcp_servers to avoid conflict with LiveKit's internal _mcp_servers handling
        self._caal_mcp_servers = mcp_servers or {}

        # n8n-specific for workflow execution (n8n uses webhook-based execution)
        self._n8n_workflow_tools = n8n_workflow_tools or []
        self._n8n_workflow_name_map = n8n_workflow_name_map or {}
        self._n8n_base_url = n8n_base_url

        # Home Assistant tools (only if HASS is connected)
        self._hass_tool_definitions = hass_tool_definitions or []
        self._hass_tool_callables = hass_tool_callables or {}

        # Callback for publishing tool status to frontend
        self._on_tool_status = on_tool_status

        # Callback for routing iOS calendar queries through the LiveKit data channel
        self._on_ios_calendar_query = on_ios_calendar_query

        # Context management: tool data cache and sliding window
        self._tool_data_cache = ToolDataCache(max_entries=tool_cache_size)
        self._max_turns = max_turns

        # Short-term memory for persistent context (MemoryTools mixin requirement)
        self._short_term_memory = short_term_memory

    async def ensure_server_live(self, server_name: str) -> mcp.MCPServerHTTP | None:
        """Return a connected MCPServerHTTP, lazy-connecting if needed."""
        entry = self._caal_mcp_servers.get(server_name)
        if entry is None:
            return None
        if isinstance(entry, LazyMCPServer):
            return await entry.ensure_connected()
        return entry  # already a real MCPServerHTTP

    def touch_server(self, server_name: str) -> None:
        """Update last-used timestamp after a successful tool call."""
        entry = self._caal_mcp_servers.get(server_name)
        if isinstance(entry, LazyMCPServer):
            entry.touch()

    async def llm_node(self, chat_ctx, tools, model_settings):
        """Custom LLM node using provider-agnostic interface."""
        user_text = _last_user_utterance_text(chat_ctx)
        if looks_like_simple_greeting(user_text):
            yield strip_markdown_for_tts(simple_greeting_response())
            return
        if looks_like_time_request(user_text):
            yield strip_markdown_for_tts(current_time_summary())
            return
        if looks_like_model_request(user_text):
            yield strip_markdown_for_tts(current_model_summary())
            return
        if looks_like_network_status_request(user_text):
            yield strip_markdown_for_tts(network_status_summary())
            return
        if looks_like_project_list_request(user_text):
            reply = await try_projects_inventory_fallback(user_text)
            if reply:
                yield strip_markdown_for_tts(reply)
                return
        async for chunk in run_llm_node(
            self,
            chat_ctx,
            provider=self._provider,
            tool_data_cache=self._tool_data_cache,
            short_term_memory=self._short_term_memory,
            max_turns=self._max_turns,
        ):
            yield chunk


# =============================================================================
# Agent Entrypoint
# =============================================================================

async def entrypoint(ctx: agents.JobContext) -> None:
    """Main entrypoint for the voice agent."""
    room_name = ctx.room.name
    acquire_deadline = time.monotonic() + _ROOM_GUARD_WAIT_SECONDS
    while True:
        async with _ROOM_GUARD_LOCK:
            busy = room_name in _ACTIVE_ROOMS or room_name in _DRAINING_ROOMS
            if not busy:
                _ACTIVE_ROOMS.add(room_name)
                break
        if time.monotonic() >= acquire_deadline:
            logger.warning(f"Room {room_name} still draining; dropping overlapping job")
            return
        await asyncio.sleep(0.25)

    # Note: Webhook server is started in background thread at agent startup (main block)
    # This ensures /setup/status is available before users connect

    # Debug: log TTS config in subprocess
    logger.info(f"[JOB] TTS Config: KOKORO_URL={KOKORO_URL}, TTS_MODEL={TTS_MODEL}")

    logger.debug(f"Joining room: {ctx.room.name}")
    await ctx.connect()

    # Load MCP server configs and wrap in lazy loaders — no connections yet.
    # n8n is connected immediately after so workflow discovery can proceed.
    mcp_configs = []
    mcp_servers: dict = {}
    try:
        mcp_configs = load_mcp_config()
        mcp_servers = prepare_lazy_mcp_servers(mcp_configs)
    except Exception as e:
        logger.error(f"Failed to load MCP config: {e}")

    # n8n needs an immediate connection for workflow tool discovery at startup.
    # All other servers stay lazy and connect on first tool use.
    n8n_workflow_tools = []
    n8n_workflow_name_map = {}
    n8n_base_url = None
    n8n_lazy = mcp_servers.get("n8n")
    if n8n_lazy:
        try:
            n8n_config = next((c for c in mcp_configs if c.name == "n8n"), None)
            if n8n_config:
                url_parts = n8n_config.url.rsplit("/", 2)
                n8n_base_url = url_parts[0] if len(url_parts) >= 2 else n8n_config.url

            n8n_mcp = await n8n_lazy.ensure_connected()
            if n8n_mcp:
                n8n_workflow_tools, n8n_workflow_name_map = await discover_n8n_workflows(
                    n8n_mcp, n8n_base_url
                )
            else:
                logger.warning("n8n MCP connect failed — workflow tools unavailable")
                import json as json_module
                try:
                    await ctx.room.local_participant.publish_data(
                        json_module.dumps({
                            "type": "mcp_error",
                            "errors": ["n8n enabled but could not connect — check URL and token in Settings"],
                        }).encode("utf-8"),
                        reliable=True,
                        topic="mcp_error",
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to discover n8n workflows: {e}")

    # Get runtime settings (from settings.json with .env fallback)
    runtime = get_runtime_settings()

    # Set GROQ_API_KEY env var for plugins that read from environment
    if runtime.get("groq_api_key"):
        os.environ["GROQ_API_KEY"] = runtime["groq_api_key"]

    # Create CAALLLM instance (provider-agnostic wrapper)
    caal_llm = CAALLLM.from_settings(runtime)

    language = runtime["language"]

    # Log configuration
    logger.info("=" * 60)
    logger.info("STARTING VOICE AGENT")
    logger.info("=" * 60)
    logger.info(f"  Language: {language}")
    if runtime["stt_provider"] == "groq":
        logger.info(f"  STT: Groq (whisper-large-v3-turbo, lang={language})")
    else:
        logger.info(f"  STT: {SPEACHES_URL} ({WHISPER_MODEL}, lang={language})")
    logger.info(f"  TTS preference: {runtime['tts_provider']}")
    llm_provider = runtime["llm_provider"]
    if llm_provider == "ollama":
        logger.info(
            f"  LLM: Ollama ({runtime['ollama_model']}, "
            f"think={runtime['think']}, num_ctx={runtime['num_ctx']})"
        )
    elif llm_provider == "groq":
        logger.info(f"  LLM: Groq ({runtime['groq_model']})")
    elif llm_provider == "openai_compatible":
        model = runtime.get("openai_model", "?")
        url = runtime.get("openai_base_url", "?")
        logger.info(f"  LLM: OpenAI-compatible ({model}, {url})")
    elif llm_provider == "openrouter":
        logger.info(
            f"  LLM: OpenRouter ({runtime.get('openrouter_model', '?')})"
        )
    logger.info(f"  MCP: {list(mcp_servers.keys()) or 'None'}")
    logger.info(
        f"  Turn detection: interruptions={runtime['allow_interruptions']}, "
        f"endpointing_delay={runtime['min_endpointing_delay']}s"
    )
    logger.info(
        f"  VAD: sample_rate={runtime['vad_sample_rate']} "
        f"activation={runtime['vad_activation_threshold']} "
        f"min_silence={runtime['vad_min_silence_duration']}s"
    )
    logger.info("=" * 60)

    # Build STT - Speaches (local) or Groq (cloud)
    if runtime["stt_provider"] == "groq":
        base_stt = groq_plugin.STT(
            model="whisper-large-v3-turbo",
            language=language,
        )
    else:
        # Whisper small.en has no concept of custom product names. Feed a
        # short vocabulary-bias prompt so it transcribes "Sonique" correctly
        # and doesn't collapse it to "Sonic" (which derails the agent into
        # Sonic-the-Hedgehog territory).
        stt_bias_prompt = (
            "The user is talking to Sonique, a self-hosted voice assistant "
            "built by Seaynic Labs. Other proper nouns in the user's "
            "vocabulary: Sonique, SoniqueBar, Seaynic, Cael, CAAL, Helmsman, "
            "Orchestr8, Enchapter, Hone."
        )
        base_stt = openai.STT(
            base_url=f"{SPEACHES_URL}/v1",
            api_key="not-needed",  # Speaches doesn't require auth
            model=WHISPER_MODEL,
            language=language,
            prompt=stt_bias_prompt,
        )

    # Load wake word settings
    all_settings = settings_module.load_settings()
    wake_word_enabled = all_settings.get("wake_word_enabled", False)

    # Session reference for wake word callback (set after session creation)
    _session_ref: AgentSession | None = None

    if wake_word_enabled:
        import json

        wake_word_model = all_settings.get("wake_word_model", "models/hey_jarvis.onnx")
        wake_word_threshold = all_settings.get("wake_word_threshold", 0.5)
        wake_word_timeout = all_settings.get("wake_word_timeout", 3.0)
        wake_greetings = get_wake_greetings(language)

        async def on_wake_detected():
            """Play wake greeting directly via TTS, bypassing agent turn-taking."""
            nonlocal _session_ref
            if _session_ref is None:
                logger.warning("Wake detected but session not ready yet")
                return

            try:
                # Pick a random greeting
                greeting = random.choice(wake_greetings)
                logger.info(f"Wake word detected, playing greeting: {greeting}")

                # Get TTS and audio output from session
                tts = _session_ref.tts
                audio_output = _session_ref.output.audio

                # Synthesize and push audio frames directly (bypasses turn-taking)
                audio_stream = tts.synthesize(greeting)
                async for event in audio_stream:
                    if hasattr(event, "frame") and event.frame:
                        await audio_output.capture_frame(event.frame)

                # Flush to complete the audio segment
                audio_output.flush()

            except Exception as e:
                logger.warning(f"Failed to play wake greeting: {e}")

        async def on_state_changed(state):
            """Publish wake word state to connected clients."""
            payload = json.dumps({
                "type": "wakeword_state",
                "state": state.value,
            })
            try:
                await ctx.room.local_participant.publish_data(
                    payload.encode("utf-8"),
                    reliable=True,
                    topic="wakeword_state",
                )
                logger.debug(f"Published wake word state: {state.value}")
            except Exception as e:
                logger.warning(f"Failed to publish wake word state: {e}")

        standby_timeout = all_settings.get("standby_timeout", 30.0)

        stt_instance = WakeWordGatedSTT(
            inner_stt=base_stt,
            model_path=wake_word_model,
            threshold=wake_word_threshold,
            silence_timeout=wake_word_timeout,
            standby_timeout=standby_timeout,
            on_wake_detected=on_wake_detected,
            on_state_changed=on_state_changed,
        )
        logger.info(
            f"  Wake word: ENABLED (model={wake_word_model}, "
            f"threshold={wake_word_threshold}, standby={standby_timeout}s)"
        )
    else:
        stt_instance = base_stt
        logger.info("  Wake word: disabled")

    # Create TTS instance based on provider (auto routes to healthiest local option)
    requested_tts_provider = runtime["tts_provider"]
    tts_provider = requested_tts_provider

    if tts_provider == "auto":
        if language == "en" and _is_kokoro_healthy():
            tts_provider = "kokoro"
        else:
            tts_provider = "piper"

    # For English sessions, prefer Kokoro when healthy unless explicitly forced to Piper.
    if (
        tts_provider == "piper"
        and language == "en"
        and os.getenv("CAAL_TTS_FORCE_PIPER", "false").lower() != "true"
        and _is_kokoro_healthy()
    ):
        logger.info("Kokoro healthy on English session; overriding Piper to Kokoro")
        tts_provider = "kokoro"

    # Auto-switch from Kokoro to Piper for non-English languages when Piper is available
    if tts_provider == "kokoro" and language != "en":
        # PIPER_URL defaults to SPEACHES_URL; if a dedicated Piper service is configured
        # (PIPER_URL != KOKORO_URL), Piper is available
        if PIPER_URL != KOKORO_URL:
            logger.info(
                f"Kokoro has limited {language} support, auto-switching to Piper"
            )
            tts_provider = "piper"
        else:
            logger.info(
                f"Kokoro TTS with {language} (no Piper service available)"
            )

    if tts_provider == "piper":
        logger.info(f"  TTS active: Piper ({runtime['tts_voice_piper']})")
    else:
        logger.info(f"  TTS active: Kokoro ({runtime['tts_voice_kokoro']})")

    if tts_provider == "piper":
        piper_voice = runtime["tts_voice_piper"]
        tts_instance = SyncOpenAITTS(
            base_url=f"{PIPER_URL}/v1",
            model=piper_voice,
            voice=piper_voice,  # caal-tts parses `voice` first; must be a real Piper voice name
            speed=TTS_SPEED,
            response_format="wav",  # caal-tts (slim stack) only emits wav
        )
    else:
        # Using SyncOpenAITTS to bypass httpx async issues in LiveKit subprocess
        kokoro_model = "kokoro"
        tts_instance = SyncOpenAITTS(
            base_url=f"{KOKORO_URL}/v1",
            model=kokoro_model,
            voice=runtime["tts_voice_kokoro"],
            speed=TTS_SPEED,
        )

    # Create session with STT and TTS (both OpenAI-compatible)
    logger.info(f"  STT instance type: {type(stt_instance).__name__}")
    logger.info(f"  STT capabilities: streaming={stt_instance.capabilities.streaming}")
    session = AgentSession(
        stt=stt_instance,
        llm=caal_llm,
        tts=tts_instance,
        vad=silero.VAD.load(
            sample_rate=runtime["vad_sample_rate"],
            activation_threshold=runtime["vad_activation_threshold"],
            min_silence_duration=runtime["vad_min_silence_duration"],
        ),
        allow_interruptions=runtime["allow_interruptions"],
        min_endpointing_delay=runtime["min_endpointing_delay"],
    )
    logger.info(f"  Session STT: {type(session.stt).__name__}")

    # Set session reference for wake word callback
    _session_ref = session

    # ==========================================================================
    # iOS bridge — request/response over LiveKit data channel
    # ==========================================================================

    _pending_calendar_future: asyncio.Future | None = None
    _pending_contacts_future: asyncio.Future | None = None
    _pending_directions_future: asyncio.Future | None = None
    _pending_location_future: asyncio.Future | None = None

    async def _ios_calendar_query(start_date: str, end_date: str) -> str:
        """Publish a calendar query to the iOS client and wait for the result."""
        nonlocal _pending_calendar_future
        import json

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_calendar_future = future

        payload = json.dumps({"start_date": start_date, "end_date": end_date})
        try:
            await ctx.room.local_participant.publish_data(
                payload.encode("utf-8"),
                reliable=True,
                topic="request_ios_calendar",
            )
        except Exception as e:
            _pending_calendar_future = None
            return json.dumps({"error": f"Failed to request iOS calendar: {e}"})

        try:
            result = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
            return json.dumps(result)
        except asyncio.TimeoutError:
            return json.dumps(
                {"error": "iOS calendar query timed out — device may not be connected."}
            )
        finally:
            _pending_calendar_future = None

    async def _ios_contacts_query(name: str) -> str:
        """Publish a contacts query to the iOS client and wait for the result."""
        nonlocal _pending_contacts_future
        import json

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_contacts_future = future

        payload = json.dumps({"name": name})
        try:
            await ctx.room.local_participant.publish_data(
                payload.encode("utf-8"),
                reliable=True,
                topic="request_ios_contacts",
            )
        except Exception as e:
            _pending_contacts_future = None
            return json.dumps({"error": f"Failed to request iOS contacts: {e}"})

        try:
            result = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
            return json.dumps(result)
        except asyncio.TimeoutError:
            return json.dumps(
                {"error": "iOS contacts query timed out — device may not be connected."}
            )
        finally:
            _pending_contacts_future = None

    async def _ios_directions_query(destination: str, transport_type: str) -> str:
        """Publish a directions query to the iOS client and wait for the result."""
        nonlocal _pending_directions_future
        import json

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_directions_future = future

        payload = json.dumps({"destination": destination, "transport_type": transport_type})
        try:
            await ctx.room.local_participant.publish_data(
                payload.encode("utf-8"),
                reliable=True,
                topic="request_ios_directions",
            )
        except Exception as e:
            _pending_directions_future = None
            return json.dumps({"error": f"Failed to request iOS directions: {e}"})

        try:
            result = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
            return json.dumps(result)
        except asyncio.TimeoutError:
            return json.dumps(
                {"error": "iOS directions query timed out — device may not be connected."}
            )
        finally:
            _pending_directions_future = None

    async def _ios_location_query() -> str:
        """Publish a location query to the iOS client and wait for the result."""
        nonlocal _pending_location_future
        import json

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_location_future = future

        try:
            await ctx.room.local_participant.publish_data(
                "{}".encode("utf-8"),
                reliable=True,
                topic="request_ios_location",
            )
        except Exception as e:
            _pending_location_future = None
            return json.dumps({"error": f"Failed to request iOS location: {e}"})

        try:
            result = await asyncio.wait_for(asyncio.shield(future), timeout=5.0)
            return json.dumps(result)
        except asyncio.TimeoutError:
            return json.dumps(
                {"error": "iOS location query timed out — device may not be connected."}
            )
        finally:
            _pending_location_future = None

    # ==========================================================================
    # Round-trip latency tracking (callbacks registered after assistant creation)
    # ==========================================================================

    _transcription_time: float | None = None

    async def _publish_tool_status(
        tool_used: bool,
        tool_names: list[str],
        tool_params: list[dict],
    ) -> None:
        """Publish tool usage status to frontend via data packet."""
        import json
        payload = json.dumps({
            "tool_used": tool_used,
            "tool_names": tool_names,
            "tool_params": tool_params,
        })

        try:
            await ctx.room.local_participant.publish_data(
                payload.encode("utf-8"),
                reliable=True,
                topic="tool_status",
            )
            logger.debug(f"Published tool status: used={tool_used}, names={tool_names}")
        except Exception as e:
            logger.warning(f"Failed to publish tool status: {e}")

    # ==========================================================================

    # Create HASS tools — REST API takes priority when credentials are present,
    # MCP-based integration is the fallback for the networked Docker stack.
    hass_tool_definitions = []
    hass_tool_callables = {}
    _ha_url = os.environ.get("HA_URL", "").strip()
    _ha_token = os.environ.get("HA_TOKEN", "").strip()
    if _ha_url and _ha_token:
        hass_tool_definitions, hass_tool_callables = create_hass_rest_tools(_ha_url, _ha_token)
        logger.info("Home Assistant tools enabled: REST (%s)", _ha_url)
    else:
        hass_lazy = mcp_servers.get("home_assistant")
        if hass_lazy:
            hass_server = await hass_lazy.ensure_connected() if isinstance(hass_lazy, LazyMCPServer) else hass_lazy
            if hass_server:
                hass_tool_prefix = await detect_hass_tool_prefix(hass_server)
                if hass_tool_prefix:
                    logger.info(f"Home Assistant MCP uses '{hass_tool_prefix}' prefix")
                hass_tool_definitions, hass_tool_callables = create_hass_tools(
                    hass_server, tool_prefix=hass_tool_prefix
                )
                logger.info("Home Assistant tools enabled: MCP")

    # Initialize short-term memory (singleton, persists across restarts)
    short_term_memory = ShortTermMemory()
    memory_count = len(short_term_memory.list_keys())
    if memory_count > 0:
        logger.info(f"Short-term memory loaded: {memory_count} entries")
    else:
        logger.info("Short-term memory initialized (empty)")

    # Create agent with CAALLLM and all MCP servers
    assistant = VoiceAssistant(
        caal_llm=caal_llm,
        language=language,
        mcp_servers=mcp_servers,
        n8n_workflow_tools=n8n_workflow_tools,
        n8n_workflow_name_map=n8n_workflow_name_map,
        n8n_base_url=n8n_base_url,
        on_tool_status=_publish_tool_status,
        tool_cache_size=runtime["tool_cache_size"],
        max_turns=runtime["max_turns"],
        hass_tool_definitions=hass_tool_definitions,
        hass_tool_callables=hass_tool_callables,
        short_term_memory=short_term_memory,
        on_ios_calendar_query=_ios_calendar_query,
    )
    # Wire iOS callbacks to the mixin
    assistant._on_ios_calendar_query = _ios_calendar_query
    assistant._on_ios_contacts_query = _ios_contacts_query
    assistant._on_ios_directions_query = _ios_directions_query
    assistant._on_ios_location_query = _ios_location_query
    # Register latency callbacks now that assistant exists — closures capture
    # `assistant` directly instead of an indirect _ref variable.
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev) -> None:
        nonlocal _transcription_time
        _transcription_time = time.perf_counter()
        logger.debug(f"User said: {ev.transcript[:80]}...")

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev) -> None:
        nonlocal _transcription_time
        if ev.new_state == "speaking" and _transcription_time is not None:
            latency_ms = (time.perf_counter() - _transcription_time) * 1000

            # Pull component breakdown from llm_node's LatencyTrace
            trace = getattr(assistant, "_last_latency_trace", None)
            if trace and trace.total_ms > 0:
                tts_ms = latency_ms - trace.total_ms
                logger.info(
                    f"VOICE_LATENCY stt_ms=na llm_ms={trace.total_ms:.0f} "
                    f"tts_gen_ms=see_TTS_METRIC tts_play_start_ms={latency_ms:.0f} "
                    f"tts_residual_ms={tts_ms:.0f} "
                    f"({trace.summary()})"
                )
            else:
                logger.info(
                    f"VOICE_LATENCY stt_ms=na llm_ms=na tts_gen_ms=see_TTS_METRIC "
                    f"tts_play_start_ms={latency_ms:.0f}"
                )

            _transcription_time = None

        # Notify wake word STT of agent state for silence timer management
        if isinstance(stt_instance, WakeWordGatedSTT):
            stt_instance.set_agent_busy(ev.new_state in ("thinking", "speaking"))

    # Create event to wait for session close (BEFORE session.start to avoid race condition)
    close_event = asyncio.Event()

    @session.on("close")
    def on_session_close(ev) -> None:
        logger.info(f"Session closed: {ev.reason}")
        close_event.set()

    # ==========================================================================
    # Webhook Command Handler (via LiveKit data channel)
    # ==========================================================================

    async def _handle_webhook_command(data: rtc.DataPacket) -> None:
        """Handle commands from webhook server via LiveKit data channel."""
        # iOS query results — resolve pending futures so the tool can return results to the LLM.
        if data.topic == "ios_calendar_result":
            nonlocal _pending_calendar_future
            if _pending_calendar_future and not _pending_calendar_future.done():
                try:
                    import json as _json
                    payload = _json.loads(data.data.decode("utf-8"))
                    _pending_calendar_future.set_result(payload)
                except Exception as e:
                    logger.warning(f"Failed to parse ios_calendar_result: {e}")
            return

        if data.topic == "ios_contacts_result":
            nonlocal _pending_contacts_future
            if _pending_contacts_future and not _pending_contacts_future.done():
                try:
                    import json as _json
                    payload = _json.loads(data.data.decode("utf-8"))
                    _pending_contacts_future.set_result(payload)
                except Exception as e:
                    logger.warning(f"Failed to parse ios_contacts_result: {e}")
            return

        if data.topic == "ios_directions_result":
            nonlocal _pending_directions_future
            if _pending_directions_future and not _pending_directions_future.done():
                try:
                    import json as _json
                    payload = _json.loads(data.data.decode("utf-8"))
                    _pending_directions_future.set_result(payload)
                except Exception as e:
                    logger.warning(f"Failed to parse ios_directions_result: {e}")
            return

        if data.topic == "ios_location_result":
            nonlocal _pending_location_future
            if _pending_location_future and not _pending_location_future.done():
                try:
                    import json as _json
                    payload = _json.loads(data.data.decode("utf-8"))
                    _pending_location_future.set_result(payload)
                except Exception as e:
                    logger.warning(f"Failed to parse ios_location_result: {e}")
            return

        if data.topic != "webhook_command":
            return

        try:
            import json

            cmd = json.loads(data.data.decode("utf-8"))
            action = cmd.get("action")
            logger.info(f"Received webhook command: {action}")

            if action in {"announce", "wake"}:
                # Stability mode: suppress command-triggered speech so only
                # normal turn responses speak. This avoids greeting/announce
                # audio colliding with active conversation playback.
                logger.info(f"Ignoring webhook command in stability mode: {action}")
                return

            elif action == "reload_tools":
                # Clear agent's internal caches
                assistant._llm_tools_cache = None

                # Clear n8n module-level cache so fresh notes are fetched
                from caal.integrations.n8n import clear_caches as clear_n8n_caches
                clear_n8n_caches()

                # Re-discover n8n workflows if MCP is available
                n8n_mcp = assistant._caal_mcp_servers.get("n8n")
                if n8n_mcp and assistant._n8n_base_url:
                    try:
                        tools, name_map = await discover_n8n_workflows(
                            n8n_mcp, assistant._n8n_base_url
                        )
                        assistant._n8n_workflow_tools = tools
                        assistant._n8n_workflow_name_map = name_map
                        logger.info(f"Reloaded {len(tools)} n8n workflows")
                    except Exception as e:
                        logger.error(f"Failed to re-discover n8n workflows: {e}")

                # Announce if requested
                if msg := cmd.get("message"):
                    await session.say(msg)
                elif tool_name := cmd.get("tool_name"):
                    await session.say(f"A new tool called '{tool_name}' is now available.")

        except Exception as e:
            logger.error(f"Failed to process webhook command: {e}")

    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket) -> None:
        """Sync wrapper for async webhook command handler."""
        asyncio.create_task(_handle_webhook_command(data))

    # Start session AFTER handlers are registered
    async def _teardown_session() -> None:
        # Resolve any pending iOS bridge callers before we tear the room down.
        for pending in (
            _pending_calendar_future,
            _pending_contacts_future,
            _pending_directions_future,
            _pending_location_future,
        ):
            if pending and not pending.done():
                pending.cancel()

        # Ensure audio pipeline and room transport are closed explicitly. Without
        # this, worker subprocesses can survive past room close and pile up.
        for method_name in ("aclose", "close", "shutdown"):
            method = getattr(session, method_name, None)
            if method is None:
                continue
            try:
                maybe_result = method()
                if asyncio.iscoroutine(maybe_result):
                    await asyncio.wait_for(maybe_result, timeout=5.0)
                break
            except Exception as e:
                logger.warning(f"session.{method_name} cleanup failed: {e}")

        try:
            room_disconnect = ctx.room.disconnect()
            if asyncio.iscoroutine(room_disconnect):
                await asyncio.wait_for(room_disconnect, timeout=5.0)
        except Exception as e:
            logger.warning(f"room disconnect cleanup failed: {e}")

    try:
        await session.start(
            room=ctx.room,
            agent=assistant,
        )

        # Brief pause so the audio channel is fully open before speaking — prevents first word cutoff
        await asyncio.sleep(0.8)

        # Stability mode: skip automatic startup speech. This prevents the
        # intro/online line from masking or replacing the first real reply.

        logger.info("Agent ready - listening for speech...")

        # Wait until session closes (room disconnects, etc.)
        await close_event.wait()
    finally:
        async with _ROOM_GUARD_LOCK:
            _ACTIVE_ROOMS.discard(room_name)
            _DRAINING_ROOMS.add(room_name)
        try:
            await _teardown_session()
        finally:
            async with _ROOM_GUARD_LOCK:
                _DRAINING_ROOMS.discard(room_name)


# =============================================================================
# Model Preloading
# =============================================================================


def preload_models():
    """Preload STT and LLM models on startup (in parallel).

    Ensures models are ready before first user connection, avoiding
    delays on first request (especially important on HDDs).

    Skips preloading entirely if wizard not complete (no provider selected yet).
    Skips individual preloads when using cloud providers (Groq).
    Note: Kokoro (remsky/kokoro-fastapi) preloads its own models at startup.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = settings_module.load_settings()

    # Skip all preloading if wizard not complete
    if not settings.get("first_launch_completed", False):
        logger.info("Skipping model preload (wizard not complete)")
        return

    stt_provider = settings.get("stt_provider", "speaches")
    llm_provider = settings.get("llm_provider", "ollama")

    logger.info("Preloading models...")
    t0 = time.perf_counter()

    def _preload_stt():
        speaches_url = os.getenv("SPEACHES_URL", "http://speaches:8000")
        whisper_model = os.getenv("WHISPER_MODEL", "Systran/faster-whisper-medium")
        try:
            logger.info(f"  Loading STT: {whisper_model}")
            response = requests.post(
                f"{speaches_url}/v1/models/{whisper_model}",
                timeout=300
            )
            if response.status_code == 404:
                response = requests.post(
                    f"{speaches_url}/v1/models?model_name={whisper_model}",
                    timeout=300
                )
            if response.status_code == 200:
                logger.info("  STT ready")
            else:
                logger.warning(f"  STT model download returned {response.status_code}")
        except Exception as e:
            logger.warning(f"  Failed to preload STT model: {e}")

    def _preload_llm():
        ollama_host = settings.get("ollama_host") or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = settings.get("ollama_model") or os.getenv("OLLAMA_MODEL", "ministral-3:8b")
        ollama_num_ctx = settings.get("num_ctx", int(os.getenv("OLLAMA_NUM_CTX", "8192")))
        try:
            logger.info(f"  Loading LLM: {ollama_model} (num_ctx={ollama_num_ctx})")
            response = requests.post(
                f"{ollama_host}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": "hi",
                    "stream": False,
                    "keep_alive": int(os.getenv("OLLAMA_KEEP_ALIVE", "-1")),
                    "options": {"num_ctx": ollama_num_ctx}
                },
                timeout=180
            )
            if response.status_code == 200:
                logger.info("  LLM ready")
            else:
                logger.warning(f"  LLM warmup returned {response.status_code}")
        except Exception as e:
            logger.warning(f"  Failed to preload LLM: {e}")

    def _preload_tts():
        language = settings.get("language", "en")
        requested_provider = settings.get("tts_provider", "auto")
        selected_provider = requested_provider

        if selected_provider == "auto":
            if language == "en" and _is_kokoro_healthy():
                selected_provider = "kokoro"
            else:
                selected_provider = "piper"

        if (
            selected_provider == "piper"
            and language == "en"
            and os.getenv("CAAL_TTS_FORCE_PIPER", "false").lower() != "true"
            and _is_kokoro_healthy()
        ):
            selected_provider = "kokoro"

        if selected_provider == "kokoro":
            tts_url = f"{os.getenv('KOKORO_URL', KOKORO_URL).rstrip('/')}/v1/audio/speech"
            voice = settings.get("tts_voice_kokoro", "am_puck")
            model = "kokoro"
        else:
            tts_url = f"{os.getenv('PIPER_URL', PIPER_URL).rstrip('/')}/v1/audio/speech"
            voice = settings.get("tts_voice_piper", "speaches-ai/piper-en_US-ryan-high")
            model = voice

        try:
            logger.info(f"  Warming TTS: {selected_provider} ({voice})")
            response = requests.post(
                tts_url,
                json={
                    "model": model,
                    "input": "ready",
                    "voice": voice,
                    "speed": TTS_SPEED,
                    "response_format": "wav",
                },
                timeout=30,
            )
            if response.status_code == 200 and response.content:
                logger.info("  TTS ready")
            else:
                logger.warning(f"  TTS warmup returned {response.status_code}")
        except Exception as e:
            logger.warning(f"  Failed to preload TTS model: {e}")

    # Run preloads in parallel (STT + LLM + TTS are independent services)
    futures = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        if stt_provider == "groq":
            logger.info("  Skipping STT preload (using Groq)")
        else:
            futures.append(pool.submit(_preload_stt))

        if llm_provider != "ollama":
            logger.info(f"  Skipping LLM preload (using {llm_provider})")
        else:
            futures.append(pool.submit(_preload_llm))

        futures.append(pool.submit(_preload_tts))

        # Wait for all preloads to complete
        for f in as_completed(futures):
            f.result()  # Surfaces any exceptions

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(f"Model preload complete in {elapsed:.0f}ms")


# =============================================================================
# Webhook Server (runs in background thread)
# =============================================================================

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8889"))


def run_webhook_server_sync():
    """Run webhook server in a separate thread (blocking).

    This starts the webhook server immediately on agent startup,
    so /setup/status and other endpoints are available before
    any user connects.
    """
    import uvicorn

    from caal.webhooks import app

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="warning",
        log_config=None,  # Don't configure logging (prevents duplicate handlers in forked workers)
    )
    server = uvicorn.Server(config)
    logger.info(f"Starting webhook server on port {WEBHOOK_PORT}")
    server.run()


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import threading

    # Start webhook server in background thread (available immediately)
    webhook_thread = threading.Thread(target=run_webhook_server_sync, daemon=True)
    webhook_thread.start()

    # Preload models before starting worker
    preload_models()

    num_idle_env = os.getenv("CAAL_NUM_IDLE_PROCESSES", "").strip()
    worker_kwargs: dict[str, object] = {
        "entrypoint_fnc": entrypoint,
        "agent_name": "caal",
        # Suppress memory warnings (models use ~1GB, this is expected)
        "job_memory_warn_mb": 0,
    }
    if num_idle_env:
        try:
            worker_kwargs["num_idle_processes"] = max(1, int(num_idle_env))
            logger.info("Worker num_idle_processes=%s", worker_kwargs["num_idle_processes"])
        except ValueError:
            logger.warning("Invalid CAAL_NUM_IDLE_PROCESSES=%r, ignoring", num_idle_env)

    agents.cli.run_app(
        agents.WorkerOptions(**worker_kwargs)
    )
