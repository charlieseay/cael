"""Unit tests for Quarterdeck router endpoint wrappers."""

from __future__ import annotations

import httpx
import pytest

from caal.integrations import router_tool


class _StubResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://localhost:5681/test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _StubAsyncClient:
    def __init__(self, scripted: list[_StubResponse], calls: list[tuple]):
        self._scripted = scripted
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, json: dict):
        self._calls.append(("POST", url, json))
        return self._scripted.pop(0)

    async def get(self, url: str, params: dict | None = None):
        self._calls.append(("GET", url, params))
        return self._scripted.pop(0)


def _patch_client(monkeypatch: pytest.MonkeyPatch, scripted: list[_StubResponse], calls: list[tuple]):
    def _factory(*_args, **_kwargs):
        return _StubAsyncClient(scripted=scripted, calls=calls)

    monkeypatch.setattr(router_tool.httpx, "AsyncClient", _factory)


@pytest.mark.asyncio
async def test_execute_route_task_posts_to_route(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []
    scripted = [_StubResponse(200, {"route": "haiku"})]
    monkeypatch.setattr(router_tool, "_router_base_url", lambda: "http://localhost:5681")
    _patch_client(monkeypatch, scripted, calls)

    out = await router_tool.execute_route_task("summarize logs", "short context")

    assert calls == [
        (
            "POST",
            "http://localhost:5681/route",
            {"task": "summarize logs", "context": "short context"},
        )
    ]
    assert '"route": "haiku"' in out


@pytest.mark.asyncio
async def test_execute_route_metrics_gets_metrics_endpoint(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []
    scripted = [_StubResponse(200, {"week": "2026-W17", "count": 12})]
    monkeypatch.setattr(router_tool, "_router_base_url", lambda: "http://localhost:5681")
    _patch_client(monkeypatch, scripted, calls)

    out = await router_tool.execute_route_metrics()

    assert calls == [("GET", "http://localhost:5681/route/metrics", None)]
    assert '"count": 12' in out


@pytest.mark.asyncio
async def test_execute_router_memory_uses_router_command_bridge(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []
    scripted = [_StubResponse(200, {"ok": True, "source": "router-command"})]
    monkeypatch.setattr(router_tool, "_router_base_url", lambda: "http://localhost:5681")
    _patch_client(monkeypatch, scripted, calls)

    out = await router_tool.execute_router_memory("soniquebar")

    assert calls == [
        ("POST", "http://localhost:5681/router", {"command": "memory", "query": "soniquebar"})
    ]
    assert '"source": "router-command"' in out


@pytest.mark.asyncio
async def test_execute_router_memory_falls_back_to_router_memory_endpoint(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple] = []
    scripted = [
        _StubResponse(404, {"error": "not found"}),
        _StubResponse(200, {"items": 4}),
    ]
    monkeypatch.setattr(router_tool, "_router_base_url", lambda: "http://localhost:5681")
    _patch_client(monkeypatch, scripted, calls)

    out = await router_tool.execute_router_memory("history")

    assert calls == [
        ("POST", "http://localhost:5681/router", {"command": "memory", "query": "history"}),
        ("GET", "http://localhost:5681/router/memory", {"query": "history"}),
    ]
    assert '"items": 4' in out


@pytest.mark.asyncio
async def test_execute_explain_route_decision_uses_route_with_explain_hint(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple] = []
    scripted = [_StubResponse(200, {"recommendation": "haiku", "confidence": 0.82})]
    monkeypatch.setattr(router_tool, "_router_base_url", lambda: "http://localhost:5681")
    _patch_client(monkeypatch, scripted, calls)

    out = await router_tool.execute_explain_route_decision("review this PR")

    assert calls == [
        (
            "POST",
            "http://localhost:5681/route",
            {"task": "review this PR", "explain": True, "source": "soniquebar"},
        )
    ]
    assert "Quarterdeck recommended 'haiku'" in out
