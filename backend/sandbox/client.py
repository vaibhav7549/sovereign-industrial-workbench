"""Talk to sandbox-runner over its Unix socket. There is no TCP fallback.

The runner listens on /ipc/runner.sock in the sandbox-ipc volume, which only the backend and the
runner mount (docker-compose.yml). The backend keeps network_mode: host, so a Docker network
cannot be shared with it; the socket file is the only way in (docs/SANDBOX.md).

All functions return a dict and never raise: errors come back as {"error": ..., "status": ...}.
"""

from __future__ import annotations

import os
from typing import Any, Dict

# Mirrors sandbox-runner/sandbox_core.py; checked here too so oversized code never leaves the backend.
MAX_CODE_BYTES = 20 * 1024
MAX_TIMEOUT_S = 10.0
_HTTP_SLACK_S = 45.0          # container start, kill, log read and queueing on top of the run timeout
_BASE = "http://sandbox-runner"   # host part is ignored on a Unix socket


def socket_path() -> str:
    return os.getenv("SANDBOX_SOCKET", "/ipc/runner.sock")


async def _call(method: str, path: str, payload: Dict[str, Any] | None, total_timeout: float) -> Dict[str, Any]:
    sock = socket_path()
    if not os.path.exists(sock):
        return {"error": f"sandbox-runner socket {sock} not found (is the sandbox-runner service running?)",
                "status": 503}
    try:
        import aiohttp

        connector = aiohttp.UnixConnector(path=sock)
        async with aiohttp.ClientSession(connector=connector,
                                         timeout=aiohttp.ClientTimeout(total=total_timeout)) as s:
            async with s.request(method, _BASE + path, json=payload) as r:
                try:
                    data = await r.json(content_type=None)
                except Exception:
                    data = {"detail": (await r.text())[:200]}
                if r.status != 200:
                    return {"error": (data or {}).get("detail") or f"HTTP {r.status}", "status": r.status}
                return data
    except Exception as e:
        return {"error": f"sandbox-runner unreachable ({type(e).__name__})", "status": 503}


async def run_code(code: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Run Python in a fresh sandbox container. Returns the runner's result or {"error", "status"}."""
    size = len((code or "").encode("utf-8"))
    if size > MAX_CODE_BYTES:
        return {"error": f"code is {size} bytes; the limit is {MAX_CODE_BYTES}", "status": 413}
    timeout = min(max(float(timeout), 0.1), MAX_TIMEOUT_S)
    return await _call("POST", "/run", {"code": code, "timeout": timeout}, timeout + _HTTP_SLACK_S)


async def health() -> Dict[str, Any]:
    return await _call("GET", "/health", None, 10.0)
