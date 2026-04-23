#!/usr/bin/env python3
"""End-to-end latency benchmark for CAAL.

Sends queries through the chat API (same llm_node as voice path, minus
STT/TTS) and collects round-trip timing.  Three probe types exercise
different pipeline paths:

  plain     - direct LLM response, no tool calls
  knowledge - triggers search_knowledge (LightRAG embedding lookup)
  tool      - triggers a lightweight tool call (e.g. memory_short)

Usage:
    python scripts/latency_bench.py                  # default: 3 runs each
    python scripts/latency_bench.py --runs 5         # 5 runs per probe
    python scripts/latency_bench.py --base-url http://192.168.1.50:8889
    python scripts/latency_bench.py --probes plain knowledge
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time

import httpx

DEFAULT_BASE = "http://localhost:8889"

PROBES: dict[str, dict] = {
    "plain": {
        "text": "Say hello in one sentence.",
        "description": "Direct LLM (no tools)",
    },
    "knowledge": {
        "text": "Search the knowledge base for information about Sonique architecture.",
        "description": "LLM + LightRAG embedding query",
    },
    "tool": {
        "text": "What do you remember from our recent conversations?",
        "description": "LLM + short-term memory lookup",
    },
}


def run_probe(
    client: httpx.Client,
    base_url: str,
    probe_name: str,
    probe: dict,
    session_id: str,
) -> dict:
    """Send one chat request and return timing data."""
    payload = {
        "text": probe["text"],
        "session_id": session_id,
        "verbose": True,
    }

    t0 = time.perf_counter()
    resp = client.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=60.0,
    )
    wall_ms = (time.perf_counter() - t0) * 1000

    if resp.status_code != 200:
        return {
            "probe": probe_name,
            "wall_ms": wall_ms,
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
        }

    data = resp.json()
    tool_names = [tc["tool"] for tc in data.get("tool_calls", [])]
    debug = data.get("debug") or {}

    return {
        "probe": probe_name,
        "wall_ms": wall_ms,
        "tools": tool_names,
        "response_len": len(data.get("response", "")),
        "prompt_tokens": debug.get("prompt_tokens", 0),
        "prompt_tokens_source": debug.get("prompt_tokens_source", "?"),
    }


def fmt_ms(values: list[float]) -> str:
    """Format a list of ms values as median (min-max)."""
    if not values:
        return "n/a"
    med = statistics.median(values)
    lo, hi = min(values), max(values)
    if len(values) == 1:
        return f"{med:.0f}ms"
    return f"{med:.0f}ms ({lo:.0f}-{hi:.0f})"


def main() -> None:
    parser = argparse.ArgumentParser(description="CAAL end-to-end latency benchmark")
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE, help=f"Chat API base URL (default: {DEFAULT_BASE})"
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="Runs per probe type (default: 3)"
    )
    parser.add_argument(
        "--probes",
        nargs="+",
        choices=list(PROBES.keys()),
        default=list(PROBES.keys()),
        help="Which probes to run (default: all)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of table"
    )
    args = parser.parse_args()

    # Verify the chat API is reachable
    client = httpx.Client()
    try:
        health = client.get(f"{args.base_url}/api/chat/sessions", timeout=5.0)
        health.raise_for_status()
    except Exception as e:
        print(f"Cannot reach chat API at {args.base_url}: {e}", file=sys.stderr)
        print("Is the agent running with the chat API enabled?", file=sys.stderr)
        sys.exit(1)

    results: dict[str, list[dict]] = {p: [] for p in args.probes}

    print(f"Running {args.runs} iterations per probe against {args.base_url}")
    print(f"Probes: {', '.join(args.probes)}")
    print()

    for run_idx in range(args.runs):
        for probe_name in args.probes:
            probe = PROBES[probe_name]
            # Fresh session each run to avoid context buildup
            session_id = f"bench-{probe_name}-{run_idx}"

            sys.stdout.write(f"  [{run_idx + 1}/{args.runs}] {probe_name}...")
            sys.stdout.flush()

            result = run_probe(client, args.base_url, probe_name, probe, session_id)
            results[probe_name].append(result)

            if "error" in result:
                print(f" ERROR: {result['error']}")
            else:
                tools = ", ".join(result["tools"]) if result["tools"] else "none"
                print(f" {result['wall_ms']:.0f}ms (tools: {tools})")

    print()

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # Summary table
    print("=" * 68)
    print(f"{'Probe':<14} {'Description':<32} {'Median (range)':<20}")
    print("-" * 68)
    for probe_name in args.probes:
        probe = PROBES[probe_name]
        times = [r["wall_ms"] for r in results[probe_name] if "error" not in r]
        print(f"{probe_name:<14} {probe['description']:<32} {fmt_ms(times):<20}")
    print("=" * 68)

    # Overall stats
    all_times = [
        r["wall_ms"] for runs in results.values() for r in runs if "error" not in r
    ]
    if all_times:
        print(f"\nOverall: {len(all_times)} successful requests")
        print(f"  Median: {statistics.median(all_times):.0f}ms")
        print(f"  p95:    {sorted(all_times)[int(len(all_times) * 0.95)]:.0f}ms")
        print(f"  Range:  {min(all_times):.0f}-{max(all_times):.0f}ms")

    errors = sum(1 for runs in results.values() for r in runs if "error" in r)
    if errors:
        print(f"\n{errors} request(s) failed.")


if __name__ == "__main__":
    main()
