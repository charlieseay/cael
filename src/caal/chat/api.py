"""Chat API router — text-in/text-out access to CAAL's LLM pipeline.

Provides HTTP endpoints that use the exact same llm_node() as the voice
path. Same system prompt, tool definitions, MCP tool resolution, provider
config, conversation history management, and tool data injection.

Endpoints:
    POST   /api/chat              - Send text, get LLM response
    DELETE /api/chat/{session_id} - Clear a session's history
    GET    /api/chat/sessions     - List active sessions

Usage:
    curl -X POST http://localhost:8889/api/chat \\
      -H "Content-Type: application/json" \\
      -d '{"text": "What are the NFL scores?", "session_id": "test-001"}'
"""

from __future__ import annotations

import asyncio
import httpx
import json
import logging
import os
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .. import CAALLLM
from .. import settings as settings_module
from ..deterministic_intents import (
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
from ..context import ChatContext, ToolContext
from ..integrations import load_mcp_config
from ..integrations.n8n import clear_caches as clear_n8n_caches
from ..llm import llm_node
from ..memory import ShortTermMemory
from ..routing.policy import policy_from_settings
from ..utils.formatting import strip_markdown_for_tts
from .session import PERSISTENT_SESSION_ID, ChatSession, ChatSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# =============================================================================
# Request / Response Models
# =============================================================================


class ChatRequest(BaseModel):
    text: str
    session_id: str | None = None
    reuse_session: bool = False
    dry_run: bool = False  # Reserved for v2
    verbose: bool = False


class ToolCallInfo(BaseModel):
    tool: str
    args: dict


class ToolResponseInfo(BaseModel):
    tool: str
    data_size: int
    data: object  # Raw tool response data (JSON arrays, dicts, etc.)


class DebugInfo(BaseModel):
    tool_responses: list[ToolResponseInfo]
    prompt_tokens: int  # Input tokens the LLM saw (real from Ollama, estimated otherwise)
    prompt_tokens_source: str  # "ollama" or "estimate"
    turn_number: int
    cached_data_arrays: int


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[ToolCallInfo]
    session_id: str
    debug: DebugInfo | None = None


class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    last_activity: float
    created_at: float


class SessionsResponse(BaseModel):
    sessions: list[SessionInfo]


class DeleteResponse(BaseModel):
    status: str
    session_id: str


class ReloadResponse(BaseModel):
    status: str
    llm_provider: str
    llm_model: str
    tools_loaded: int
    sessions_cleared: int


# =============================================================================
# Module State (lazy-initialized on first request)
# =============================================================================

_init_lock = asyncio.Lock()
_session_manager: ChatSessionManager | None = None
_tool_context: ToolContext | None = None
_llm: CAALLLM | None = None
_prompt: str | None = None
_short_term_memory: ShortTermMemory | None = None
_max_turns: int = 20

# Serialize llm_node() calls — it mutates agent._llm_tools_cache
_request_lock = asyncio.Lock()
_LEAKED_TOOL_PREFIX_RE = re.compile(r"^:\w+\([^)]*\):\s*", re.MULTILINE)


def _get_runtime_settings() -> dict:
    """Build runtime settings matching voice_agent.py's get_runtime_settings().

    Priority: settings.json (explicit) > .env > defaults.
    Only includes fields needed for LLM + chat (no TTS/STT/audio).
    """
    settings = settings_module.load_settings()
    user_settings = settings_module.load_user_settings()
    ollama_think = os.getenv("OLLAMA_THINK", "false").lower() == "true"

    return {
        "language": settings.get("language", "en"),
        # LLM Provider
        "llm_provider": (
            user_settings.get("llm_provider")
            or os.getenv("LLM_PROVIDER", "ollama")
        ),
        "temperature": settings.get(
            "temperature", float(os.getenv("OLLAMA_TEMPERATURE", "0.15"))
        ),
        # Ollama
        "ollama_host": (
            user_settings.get("ollama_host")
            or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ),
        "ollama_model": (
            user_settings.get("ollama_model")
            or os.getenv("OLLAMA_MODEL", "ministral-3:8b")
        ),
        "num_ctx": settings.get(
            "num_ctx", int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        ),
        "think": ollama_think,
        # Groq
        "groq_api_key": (
            settings.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")
        ),
        "groq_model": (
            user_settings.get("groq_model")
            or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        ),
        # OpenAI-compatible
        "openai_base_url": (
            user_settings.get("openai_base_url")
            or os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
        ),
        "openai_api_key": (
            settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
        ),
        "openai_model": (
            user_settings.get("openai_model") or os.getenv("OPENAI_MODEL", "")
        ),
        # OpenRouter
        "openrouter_api_key": (
            settings.get("openrouter_api_key")
            or os.getenv("OPENROUTER_API_KEY", "")
        ),
        "openrouter_model": (
            user_settings.get("openrouter_model")
            or os.getenv("OPENROUTER_MODEL", "openai/gpt-4")
        ),
        # Claude CLI (subscription-native)
        "claude_cli_model": (
            user_settings.get("claude_cli_model")
            or os.getenv("CLAUDE_CLI_MODEL", "claude-haiku-4-5")
        ),
        # Cursor CLI (subscription-native)
        "cursor_cli_model": (
            user_settings.get("cursor_cli_model")
            or os.getenv("CURSOR_CLI_MODEL", "")
        ),
        # Anthropic API
        "anthropic_api_key": (
            settings.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")
        ),
        "anthropic_model": (
            user_settings.get("anthropic_model")
            or os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        ),
        # Gemini CLI (subscription-native)
        "gemini_cli_model": (
            user_settings.get("gemini_cli_model")
            or os.getenv("GEMINI_CLI_MODEL", "gemini-2.0-flash")
        ),
        # Google AI API
        "google_api_key": (
            settings.get("google_api_key") or os.getenv("GOOGLE_API_KEY", "")
        ),
        "google_model": (
            user_settings.get("google_model")
            or os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
        ),
        # Router tier config (kept in sync with voice path)
        "router_simple_provider": settings.get("router_simple_provider", "ollama"),
        "router_simple_model": settings.get("router_simple_model", "qwen3:4b"),
        "router_medium_provider": settings.get("router_medium_provider", "ollama"),
        "router_medium_model": settings.get("router_medium_model", "qwen3:8b"),
        "router_complex_provider": settings.get("router_complex_provider", "claude_cli"),
        "router_complex_model": settings.get("router_complex_model", "claude-haiku-4-5"),
        # Shared
        "max_turns": settings.get(
            "max_turns", int(os.getenv("OLLAMA_MAX_TURNS", "20"))
        ),
        "tool_cache_size": settings.get(
            "tool_cache_size", int(os.getenv("TOOL_CACHE_SIZE", "3"))
        ),
    }


async def _ensure_initialized() -> None:
    """Lazy initialization of LLM, tools, and session manager.

    Called on first request. Same initialization as voice_agent.py
    entrypoint but without audio (no STT, TTS, LiveKit).
    """
    global _session_manager, _tool_context, _llm, _prompt
    global _short_term_memory, _max_turns

    # Fast path — already initialized
    if _llm is not None:
        return

    async with _init_lock:
        # Double-check after acquiring lock
        if _llm is not None:
            return

        logger.info("Initializing chat API...")

        runtime = _get_runtime_settings()
        _max_turns = runtime["max_turns"]

        # Create LLM provider (same as voice path)
        _llm = CAALLLM.from_settings(runtime)
        logger.info(
            f"  LLM: {runtime['llm_provider']} "
            f"({runtime.get('ollama_model', '')})"
        )

        # Load system prompt with date/time context
        # CHAT_PROMPT selects a named prompt file (e.g. "headless" → prompt/en/headless.md)
        timezone_id = os.getenv("TIMEZONE", "America/Los_Angeles")
        timezone_display = os.getenv("TIMEZONE_DISPLAY", "Pacific Time")
        chat_prompt_name = os.getenv("CHAT_PROMPT") or None
        _prompt = settings_module.load_prompt_with_context(
            timezone_id=timezone_id,
            timezone_display=timezone_display,
            language=runtime.get("language", "en"),
            prompt_name=chat_prompt_name,
        )

        # Short-term memory (shared singleton, reload for cross-process sync)
        _short_term_memory = ShortTermMemory()
        _short_term_memory.reload()

        # Initialize tool context (MCP servers, n8n, HASS, memory, web_search)
        mcp_configs = load_mcp_config()
        _tool_context = ToolContext(
            mcp_configs=mcp_configs,
            short_term_memory=_short_term_memory,
            provider=_llm.provider_instance,
        )
        await _tool_context.ensure_mcp_initialized()

        # Session manager with background cleanup
        _session_manager = ChatSessionManager()
        await _session_manager.start()

        logger.info("Chat API initialized")


# =============================================================================
# Debug Helpers
# =============================================================================


def _estimate_tokens(text: str) -> int:
    """Estimate token count using word-based heuristic.

    English text averages ~1.3 tokens per word (subword tokenization).
    More accurate than chars/4 for mixed content with JSON, code, etc.
    """
    words = len(text.split())
    return int(words * 1.3)


def _looks_like_routing_policy_request(text: str) -> bool:
    t = (text or "").lower()
    return "routing policy" in t or ("routing" in t and "tier" in t)


def _routing_policy_response_text() -> str:
    runtime = _get_runtime_settings()
    policy = policy_from_settings(runtime)
    tiers = policy.get("tiers", [])
    parts = []
    for tier in tiers:
        parts.append(
            f"{tier.get('label','tier')} -> {tier.get('provider','unknown')} ({tier.get('model','unknown')})"
        )
    return "Current Sonique routing policy: " + "; ".join(parts)


def _sanitize_response_text(text: str) -> str:
    cleaned = _LEAKED_TOOL_PREFIX_RE.sub("", text or "").strip()
    return cleaned or (text or "")


def _build_debug_info(
    *,
    session: ChatSession,
    prompt: str,
    cache_ts_before: set[float],
    memory: ShortTermMemory | None,
    tool_context: ToolContext | None,
    provider_usage=None,
) -> DebugInfo:
    """Build verbose debug info matching what llm_node sees in context.

    Uses real token counts from Ollama when available (prompt_eval_count),
    falls back to word-based estimation for other providers.
    """
    # Tool responses from this turn (entries with timestamps not in snapshot)
    new_cache_entries = [
        e for e in session.tool_data_cache._cache
        if e["timestamp"] not in cache_ts_before
    ]
    tool_responses = []
    for entry in new_cache_entries:
        data = entry.get("data")
        data_str = json.dumps(data) if data is not None else ""
        tool_responses.append(
            ToolResponseInfo(
                tool=entry["tool"],
                data_size=len(data_str),
                data=data,
            )
        )

    # Token count: prefer real counts from Ollama, fall back to estimate
    if provider_usage and hasattr(provider_usage, "prompt_tokens"):
        prompt_tokens = provider_usage.prompt_tokens
        source = "ollama"
    else:
        # Estimate from message content + tool definitions
        context_parts: list[str] = [prompt]

        cache_context = session.tool_data_cache.get_context_message()
        if cache_context:
            context_parts.append(cache_context)

        if memory:
            mem_context = memory.get_context_message()
            if mem_context:
                context_parts.append(mem_context)

        for msg in session.get_messages():
            context_parts.append(msg.get("content", ""))

        prompt_tokens = _estimate_tokens(" ".join(context_parts))

        if tool_context and tool_context._llm_tools_cache:
            tool_defs_str = json.dumps(tool_context._llm_tools_cache)
            prompt_tokens += _estimate_tokens(tool_defs_str)

        source = "estimate"

    return DebugInfo(
        tool_responses=tool_responses,
        prompt_tokens=prompt_tokens,
        prompt_tokens_source=source,
        turn_number=len(session.messages) // 2,  # user+assistant pairs
        cached_data_arrays=len(session.tool_data_cache._cache),
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Send text to LLM and get response with tool calls.

    Uses the exact same llm_node() as the voice path — same prompt,
    tools, provider, conversation history, and tool data injection.
    """
    await _ensure_initialized()
    assert _session_manager is not None
    assert _tool_context is not None
    assert _llm is not None
    assert _prompt is not None

    if looks_like_project_list_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        projects_fallback = await try_projects_inventory_fallback(req.text)
        return ChatResponse(
            response=projects_fallback or "Project inventory is unavailable right now.",
            tool_calls=[],
            session_id=sid,
            debug=None,
        )

    if looks_like_simple_greeting(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        return ChatResponse(
            response=simple_greeting_response(),
            tool_calls=[],
            session_id=sid,
            debug=None,
        )

    if looks_like_time_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        return ChatResponse(
            response=current_time_summary(),
            tool_calls=[],
            session_id=sid,
            debug=None,
        )

    if looks_like_model_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        return ChatResponse(
            response=current_model_summary(),
            tool_calls=[],
            session_id=sid,
            debug=None,
        )

    if looks_like_network_status_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        return ChatResponse(
            response=network_status_summary(),
            tool_calls=[],
            session_id=sid,
            debug=None,
        )

    if _looks_like_routing_policy_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        return ChatResponse(
            response=_routing_policy_response_text(),
            tool_calls=[],
            session_id=sid,
            debug=None,
        )

    # Resolve session: explicit id > reuse latest > create new
    sid = req.session_id
    if sid is None and req.reuse_session:
        latest = _session_manager.get_latest_session()
        if latest is not None:
            sid = latest.session_id

    session = _session_manager.get_or_create(
        session_id=sid, max_turns=_max_turns
    )

    # Add user message to session history
    session.add_message(role="user", content=req.text)

    projects_fallback = await try_projects_inventory_fallback(req.text)
    if projects_fallback:
        session.add_message(role="assistant", content=projects_fallback)
        return ChatResponse(
            response=projects_fallback,
            tool_calls=[],
            session_id=session.session_id,
            debug=None,
        )

    # Build chat context (same structure as voice path)
    chat_ctx = ChatContext(
        system_prompt=_prompt,
        messages=session.get_messages(),
    )

    # Reload short-term memory for cross-process sync
    if _short_term_memory:
        _short_term_memory.reload()

    # Track tool calls via _on_tool_status callback (captures ALL tools,
    # including those returning strings like HASS tools)
    tool_calls_log: list[ToolCallInfo] = []

    async def _capture_tool_status(
        used: bool, names: list[str], params: list[dict]
    ) -> None:
        if used:
            tool_calls_log.clear()  # Replace — callback accumulates across rounds
            for name, param in zip(names, params):
                tool_calls_log.append(ToolCallInfo(tool=name, args=param or {}))

    # Capture real token usage from provider (Ollama reports exact counts)
    captured_usage = None

    def _capture_usage(usage) -> None:
        nonlocal captured_usage
        captured_usage = usage

    # Snapshot cache timestamps before call (for verbose tool_responses diff)
    # Can't use len() — ToolDataCache evicts oldest when full, so length
    # stays constant after max_entries and _cache[len_before:] returns [].
    cache_ts_before = {e["timestamp"] for e in session.tool_data_cache._cache}

    # Call llm_node — same code path as voice
    response_chunks: list[str] = []
    async with _request_lock:
        # Set callbacks while we hold the lock (safe — one request at a time)
        _tool_context._on_tool_status = _capture_tool_status
        _tool_context._on_usage = _capture_usage
        try:
            async for chunk in llm_node(
                agent=_tool_context,
                chat_ctx=chat_ctx,
                provider=_llm.provider_instance,
                tool_data_cache=session.tool_data_cache,
                short_term_memory=_short_term_memory,
                max_turns=_max_turns,
            ):
                response_chunks.append(chunk)
            # Let pending _on_tool_status tasks complete
            await asyncio.sleep(0)
        finally:
            _tool_context._on_tool_status = None
            _tool_context._on_usage = None

    response_text = _sanitize_response_text(
        strip_markdown_for_tts("".join(response_chunks)).strip()
    )
    tool_calls = list(tool_calls_log)

    # Add assistant response to session history
    session.add_message(role="assistant", content=response_text)

    # Build debug info if verbose
    debug = None
    if req.verbose:
        debug = _build_debug_info(
            session=session,
            prompt=_prompt,
            cache_ts_before=cache_ts_before,
            memory=_short_term_memory,
            tool_context=_tool_context,
            provider_usage=captured_usage,
        )

    return ChatResponse(
        response=response_text,
        tool_calls=tool_calls,
        session_id=session.session_id,
        debug=debug,
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Same as POST /api/chat but streams tokens as Server-Sent Events.

    Each event:  data: {"text": "<chunk>"}
    Final event: data: [DONE]

    SoniqueBar uses this for the keyboard chat window so text appears
    in real-time as Cael responds.
    """
    await _ensure_initialized()
    assert _session_manager is not None
    assert _tool_context is not None
    assert _llm is not None
    assert _prompt is not None

    if looks_like_project_list_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        text = await try_projects_inventory_fallback(req.text) or "Project inventory is unavailable right now."

        async def projects_guard_generate():
            yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            projects_guard_generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Session-Id": sid,
            },
        )

    if looks_like_network_status_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID
        text = network_status_summary()

        async def network_guard_generate():
            yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            network_guard_generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Session-Id": sid,
            },
        )

    if _looks_like_routing_policy_request(req.text):
        sid = req.session_id or PERSISTENT_SESSION_ID

        async def generate_policy():
            text = _routing_policy_response_text()
            yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_policy(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Session-Id": sid,
            },
        )

    sid = req.session_id
    if sid is None and req.reuse_session:
        latest = _session_manager.get_latest_session()
        if latest is not None:
            sid = latest.session_id

    session = _session_manager.get_or_create(session_id=sid, max_turns=_max_turns)
    session.add_message(role="user", content=req.text)

    projects_fallback = await try_projects_inventory_fallback(req.text)
    if projects_fallback:
        session.add_message(role="assistant", content=projects_fallback)

        async def generate_projects():
            yield f"data: {json.dumps({'text': projects_fallback})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_projects(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Session-Id": session.session_id,
            },
        )

    chat_ctx = ChatContext(
        system_prompt=_prompt,
        messages=session.get_messages(),
    )

    if _short_term_memory:
        _short_term_memory.reload()

    collected: list[str] = []

    async def generate():
        async with _request_lock:
            try:
                async for chunk in llm_node(
                    agent=_tool_context,
                    chat_ctx=chat_ctx,
                    provider=_llm.provider_instance,
                    tool_data_cache=session.tool_data_cache,
                    short_term_memory=_short_term_memory,
                    max_turns=_max_turns,
                ):
                    collected.append(chunk)
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                await asyncio.sleep(0)
            except Exception as e:
                logger.error(f"chat_stream error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        full_response = _sanitize_response_text("".join(collected))
        session.add_message(role="assistant", content=full_response)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Session-Id": session.session_id,
        },
    )


@router.get("/history")
async def chat_history(session_id: str = PERSISTENT_SESSION_ID) -> dict:  # type: ignore[assignment]
    """Return the message history for a session.

    Defaults to the canonical persistent session so SoniqueBar can load
    the full conversation on chat window open.
    """
    await _ensure_initialized()
    assert _session_manager is not None
    session = _session_manager.get_or_create(session_id=session_id, max_turns=_max_turns)
    return {
        "session_id": session.session_id,
        "messages": session.get_messages(),
        "message_count": len(session.messages),
    }


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions() -> SessionsResponse:
    """List active chat sessions."""
    await _ensure_initialized()
    assert _session_manager is not None

    sessions = _session_manager.list_sessions()
    return SessionsResponse(
        sessions=[SessionInfo(**s) for s in sessions]
    )


@router.delete("/{session_id}", response_model=DeleteResponse)
async def delete_session(session_id: str) -> DeleteResponse:
    """Clear a session's history."""
    await _ensure_initialized()
    assert _session_manager is not None

    deleted = _session_manager.delete(session_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Session not found: {session_id}"
        )
    return DeleteResponse(status="deleted", session_id=session_id)


@router.post("/voice", response_class=Response)
async def chat_voice(req: ChatRequest) -> Response:
    """Text in → WAV audio out. Designed for Siri Shortcuts and PWA clients.

    Same LLM pipeline as the voice path. Response is synthesized via Kokoro
    (or Speaches fallback) and returned as audio/wav.

    Session ID is returned in the X-Session-Id response header so clients
    can maintain conversation continuity across turns.

    Example Siri Shortcut flow:
        POST /api/chat/voice {"text": "what's pending?", "session_id": "iphone"}
        → audio/wav bytes → play on device

    Args:
        req: ChatRequest (text, optional session_id, optional reuse_session)

    Returns:
        WAV audio bytes with headers:
            X-Session-Id: session UUID
            X-Response-Text: plain-text LLM response (for display/logging)
    """
    from ..tts.synthesizer import synthesize

    # Run through LLM pipeline (same as /api/chat)
    chat_response = await chat(req)

    # Synthesize response text to audio
    try:
        # Embedded runtime must prioritize local Piper even if persisted settings
        # still contain legacy providers from prior Docker-era sessions.
        forced_provider = (os.getenv("TTS_PROVIDER") or "").strip().lower() or None
        audio_bytes = await synthesize(chat_response.response, provider=forced_provider)
    except Exception as e:
        logger.error(f"TTS synthesis failed for voice endpoint: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"TTS unavailable: {e}",
        )

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "X-Session-Id": chat_response.session_id,
            "X-Response-Text": chat_response.response[:500],  # truncated for header safety
        },
    )


@router.post("/reload", response_model=ReloadResponse)
async def reload_chat() -> ReloadResponse:
    """Reload LLM, tools, and prompt from current settings.

    Clears all sessions and re-initializes everything from scratch.
    Use after changing LLM provider/model, adding n8n workflows,
    or updating the system prompt.
    """
    global _session_manager, _tool_context, _llm, _prompt
    global _short_term_memory, _max_turns

    sessions_cleared = 0

    async with _init_lock:
        # Stop existing session manager
        if _session_manager is not None:
            sessions_cleared = len(_session_manager.list_sessions())
            await _session_manager.stop()

        # Reset all state so _ensure_initialized runs fresh
        _session_manager = None
        _tool_context = None
        _llm = None
        _prompt = None
        _short_term_memory = None

    # Force settings + n8n cache reload before re-init
    settings_module.reload_settings()
    clear_n8n_caches()

    # Re-initialize from current settings
    await _ensure_initialized()
    assert _llm is not None
    assert _tool_context is not None

    runtime = _get_runtime_settings()

    # Count discovered tools
    tools_loaded = (
        len(_tool_context._n8n_workflow_tools)
        + len(_tool_context._hass_tool_definitions)
        + sum(
            1
            for name, server in _tool_context._caal_mcp_servers.items()
            if name not in ("n8n", "home_assistant")
        )
    )

    logger.info(
        f"Chat API reloaded: {runtime['llm_provider']} "
        f"({runtime.get('ollama_model', '')}), "
        f"{tools_loaded} tools, {sessions_cleared} sessions cleared"
    )

    return ReloadResponse(
        status="reloaded",
        llm_provider=runtime["llm_provider"],
        llm_model=(
            runtime.get("ollama_model")
            or runtime.get("groq_model")
            or runtime.get("openai_model")
            or runtime.get("openrouter_model")
            or ""
        ),
        tools_loaded=tools_loaded,
        sessions_cleared=sessions_cleared,
    )
