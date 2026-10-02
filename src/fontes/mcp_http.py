"""Minimal call to a remote MCP server (Streamable HTTP) without the SDK: initialize + tools/call.

Used for Kiwi and Seats.aero, which need no session. The raw response goes to the normalizer
without passing through the model's context.
"""

from __future__ import annotations

import json

import httpx

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-06-18",
}


class ErroMCP(RuntimeError):
    pass


def _rpc(http: httpx.Client, url: str, metodo: str, params: dict, id_: int, headers: dict) -> dict:
    r = http.post(url, headers=headers, json={"jsonrpc": "2.0", "id": id_, "method": metodo, "params": params})
    r.raise_for_status()
    corpo = r.text
    if "text/event-stream" in r.headers.get("content-type", ""):
        dados = [l[5:].strip() for l in corpo.splitlines() if l.startswith("data:")]
        corpo = dados[-1] if dados else "{}"
    msg = json.loads(corpo)
    if "error" in msg:
        raise ErroMCP(str(msg["error"]))
    return msg["result"]


def chamar_tool(url: str, tool: str, argumentos: dict, http: httpx.Client | None = None, timeout: float = 60) -> dict:
    """Return the tools/call `result`. Raises ErroMCP if the tool reports an error."""
    http = http or httpx.Client(timeout=timeout)
    headers = dict(HEADERS)
    init = http.post(url, headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "farehunter", "version": "0.1"}},
    })
    init.raise_for_status()
    if sid := init.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = sid
    res = _rpc(http, url, "tools/call", {"name": tool, "arguments": argumentos}, 2, headers)
    if res.get("isError"):
        textos = " ".join(c.get("text", "") for c in res.get("content", []))
        raise ErroMCP(textos[:400])
    return res


def json_do_resultado(res: dict) -> dict:
    """structuredContent if present; otherwise the first text block that is JSON."""
    if isinstance(res.get("structuredContent"), dict):
        return res["structuredContent"]
    for c in res.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                continue
    raise ErroMCP("resposta sem JSON")
