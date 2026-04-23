"""LightRAG knowledge base tool for CAAL.

Provides query and write access to the LightRAG graph-RAG service,
which indexes the Obsidian vault and grows organically from conversations.

Two tools:
  search_knowledge — retrieve context from the knowledge graph
  store_knowledge  — persist new facts to the vault so LightRAG indexes them

The vault is mounted read-write at /vault inside the container.
Facts are appended to /vault/Projects/Lab/Apps/Sonique/learned-facts.md.
After writing, /index/refresh is called on LightRAG to update the graph.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from livekit.agents import function_tool

logger = logging.getLogger(__name__)

LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://host.docker.internal:8128")
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
FACTS_FILE = VAULT_PATH / "Projects/Lab/Apps/Sonique/learned-facts.md"
_QUERY_TIMEOUT = 8.0
_WRITE_TIMEOUT = 15.0
_TOP_K = 6


async def _query(text: str) -> list[dict]:
    """Fetch top-k chunks from LightRAG with no server-side LLM synthesis.

    LightRAG's internal synthesis path runs qwen2.5:14b locally and takes 10-15s.
    We skip it and let the main voice LLM (Claude) synthesize from the raw chunks.
    Returns a list of {source, chunk, similarity, content} dicts.
    """
    async with httpx.AsyncClient(timeout=_QUERY_TIMEOUT) as client:
        resp = await client.post(
            f"{LIGHTRAG_URL}/query",
            json={"query": text, "top_k": _TOP_K, "synthesize": False},
        )
        resp.raise_for_status()
        return resp.json().get("sources", [])


def _append_fact(fact: str) -> None:
    """Append a timestamped fact to the vault knowledge file."""
    FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not FACTS_FILE.exists():
        header = (
            "---\n"
            "tags: [sonique, knowledge, learned-facts]\n"
            "created: " + datetime.now().strftime("%Y-%m-%d") + "\n"
            "updated: " + datetime.now().strftime("%Y-%m-%d") + "\n"
            "status: active\n"
            "---\n\n"
            "# Sonique Learned Facts\n\n"
            "Facts Sonique has learned from conversations with Charlie.\n"
            "Updated automatically — do not edit by hand.\n\n"
        )
        FACTS_FILE.write_text(header, encoding="utf-8")

    with FACTS_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- [{timestamp}] {fact}\n")


async def _refresh_index() -> None:
    """Tell LightRAG to reindex the vault after a write."""
    try:
        async with httpx.AsyncClient(timeout=_WRITE_TIMEOUT) as client:
            await client.post(f"{LIGHTRAG_URL}/index/refresh")
    except Exception as e:
        logger.warning(f"LightRAG index refresh failed (non-fatal): {e}")


class LightRAGTools:
    """Mixin providing LightRAG search and store tools.

    No instance state required — all calls go over HTTP to the LightRAG service
    or directly to the vault filesystem.
    """

    @function_tool
    async def search_knowledge(self, query: str) -> str:
        """Search the personal knowledge base for context about people, projects, preferences, or past decisions.

        Use this when the user asks about something that might be in the vault
        or was learned from a previous conversation — projects, notes, personal preferences,
        technical details, or anything that might have been stored before.

        Do NOT use for real-time data like weather, scores, or live prices — use web_search for those.

        Args:
            query: Natural language keyword query. Prefer specific terms (project or tool names, file names)
                   over abstract phrasings. "Helmsman architecture" works better than "who is Helmsman".

        Returns:
            Relevant chunks from the knowledge base, each with its source path. Read them to answer the user.
        """
        logger.info(f"search_knowledge: {query!r}")
        try:
            sources = await _query(query)
        except Exception as e:
            logger.warning(f"LightRAG query failed: {e}")
            return "Knowledge base is temporarily unavailable."

        if not sources:
            return "Nothing found in the knowledge base for that query."

        # Format chunks for the LLM — source path header, then content.
        # Keep total length reasonable for voice context.
        blocks = []
        for s in sources:
            similarity = s.get("similarity", 0)
            if similarity < 0.55:
                continue
            header = f"[{s.get('source', '?')}  similarity={similarity}]"
            content = (s.get("content", "") or "").strip()
            if content:
                blocks.append(f"{header}\n{content}")

        if not blocks:
            return "Nothing relevant found in the knowledge base."

        return "\n\n---\n\n".join(blocks)

    @function_tool
    async def store_knowledge(self, fact: str) -> str:
        """Store a new fact into the personal knowledge base for future reference across sessions.

        Use this when you learn something meaningful about Charlie, his projects, preferences,
        or decisions that isn't already known — something worth remembering long-term.

        Keep facts concise and factual. Do not store trivial conversational filler.

        Good facts to store:
        - "Charlie prefers dark mode on all his apps"
        - "The Hone project uses Astro SSR and Stripe for payments"
        - "Charlie's daughter's wedding is in June 2026"

        Args:
            fact: A single clear factual statement to add to the knowledge base.

        Returns:
            Confirmation that the fact was stored, or an error message.
        """
        logger.info(f"store_knowledge: {fact!r}")
        try:
            _append_fact(fact)
            await _refresh_index()
            return f"Stored: {fact}"
        except Exception as e:
            logger.warning(f"store_knowledge failed: {e}")
            return f"Could not store fact: {e}"
