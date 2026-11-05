"""Task 3: sandbox client, run_python_sandboxed tool, and real isolation checks.

The isolation tests run real code in real sandbox containers through sandbox-runner. They skip
unless the runner socket is reachable and reports Docker plus the sandbox image, which is the case
inside the backend container with the stack up:

    docker compose up -d --build backend sandbox-runner
    docker compose exec backend python -m pytest -q -rs tests/test_sandbox.py
"""

import asyncio
import json
import os

import pytest

from sandbox import client
from tools import core
from tools.core import ToolDeps


def run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------------- client (no runner needed)
def test_client_rejects_oversized_code_without_contacting_runner(monkeypatch):
    monkeypatch.setenv("SANDBOX_SOCKET", "/nonexistent/should-not-be-touched.sock")
    res = run(client.run_code("#" * (20 * 1024 + 1)))
    assert res["status"] == 413 and "limit is 20480" in res["error"]


def test_client_reports_missing_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_SOCKET", str(tmp_path / "missing.sock"))
    res = run(client.run_code("print(1)"))
    assert res["status"] == 503 and "not found" in res["error"]


def test_client_has_no_tcp_fallback():
    import inspect

    src = inspect.getsource(client)
    assert "UnixConnector" in src and "TCPConnector" not in src and "localhost" not in src


# ----------------------------------------------------------------------------- tool (fake sandbox)
def _deps(sandbox_run):
    async def unused(*a, **k):
        raise AssertionError("not used")

    return ToolDeps(actor="op", mcp_call=unused, summarize=unused, ingest_bytes=unused, sandbox_run=sandbox_run)


def test_tool_without_sandbox_configured():
    assert "not configured" in json.loads(run(core.run_python_sandboxed_impl(_deps(None), "print(1)")))["error"]


def test_tool_returns_only_result_fields():
    async def fake(code, timeout):
        assert (code, timeout) == ("print(1+1)", 3.0)
        return {"exit_code": 0, "stdout": "2\n", "stderr": "", "timed_out": False, "truncated": False,
                "oom_killed": False, "duration_ms": 412, "limits": {"x": 1}, "internal": "dropped"}

    out = json.loads(run(core.run_python_sandboxed_impl(_deps(fake), "print(1+1)", 3)))
    assert out["stdout"] == "2\n" and set(out) == set(core.SANDBOX_RESULT_KEYS)


def test_tool_passes_errors_through():
    async def fake(code, timeout):
        return {"error": "sandbox-runner unreachable (ClientConnectorError)", "status": 503}

    assert "unreachable" in json.loads(run(core.run_python_sandboxed_impl(_deps(fake), "1")))["error"]


# ----------------------------------------------------------------------------- real sandbox
def _runner_ready():
    if not os.path.exists(client.socket_path()):
        return False, f"sandbox-runner socket {client.socket_path()} not present"
    try:
        h = run(client.health())
    except Exception as e:  # aiohttp missing etc.
        return False, f"health check failed: {type(e).__name__}"
    if "error" in h:
        return False, f"sandbox-runner not ready: {h['error']}"
    if not h.get("docker") or not h.get("image_present"):
        return False, f"sandbox-runner not ready: {h}"
    return True, ""


READY, WHY = _runner_ready()
requires_runner = pytest.mark.skipif(not READY, reason=WHY or "sandbox-runner not reachable")


def sandbox(code, timeout=5):
    res = run(client.run_code(code, timeout))
    assert "error" not in res, res
    return res


@requires_runner
def test_hello_runs_as_nobody_without_capabilities():
    res = sandbox("import os\nprint(1+1)\nprint(os.getuid(), os.getgid())\n"
                  "print([l for l in open('/proc/self/status') if l.startswith('CapEff')][0].split()[1])")
    assert res["exit_code"] == 0
    assert res["stdout"].split() == ["2", "65534", "65534", "0000000000000000"]


@requires_runner
def test_host_paths_are_not_reachable():
    code = r'''
import os
for p in ["/var/run/docker.sock", "/ipc/runner.sock", "/data", "/app/main.py", "/app/.env", "/certs",
          "/host", "/proc/1/root/var/run/docker.sock"]:
    print(p, os.path.exists(p))
# /etc/passwd inside the sandbox is the image's own file: no host accounts (uid 1000-65533).
users = [l.split(":") for l in open("/etc/passwd")]
print("host_users", [u[0] for u in users if 1000 <= int(u[2]) < 65534])
for target in ["/etc/pwned", "/pwned", "/usr/lib/pwned"]:
    try:
        open(target, "w").write("x"); print(target, "WRITABLE")
    except OSError as e:
        print(target, "blocked", e.errno)
open("/work/ok.txt", "w").write("ok"); print("work", open("/work/ok.txt").read())
'''
    lines = sandbox(code)["stdout"].splitlines()
    for line in lines[:8]:
        assert line.endswith(" False"), line          # none of the host/backend paths exist in the sandbox
    assert "host_users []" in lines
    assert all("blocked" in l for l in lines if l.startswith(("/etc/pwned", "/pwned", "/usr/lib/pwned")))
    assert "work ok" in lines


@requires_runner
def test_outbound_socket_fails():
    code = r'''
import socket
for host, port in [("1.1.1.1", 53), ("8.8.8.8", 443), ("172.17.0.1", 2375)]:
    try:
        socket.create_connection((host, port), timeout=3); print(host, "CONNECTED")
    except OSError as e:
        print(host, "blocked", type(e).__name__)
try:
    socket.getaddrinfo("example.com", 443); print("dns RESOLVED")
except OSError as e:
    print("dns blocked")
print("interfaces", sorted(n for _, n in socket.if_nameindex()))
'''
    out = sandbox(code)["stdout"]
    assert "CONNECTED" not in out and "RESOLVED" not in out
    assert out.count("blocked") == 4
    assert "interfaces ['lo']" in out                  # loopback only: --network none


@requires_runner
def test_infinite_loop_killed_within_timeout():
    res = sandbox("while True: pass", timeout=2)
    assert res["timed_out"] is True and res["exit_code"] is None
    assert res["duration_ms"] < 2000 + 7000            # timeout + kill and container start slack


@requires_runner
def test_large_output_truncated_at_cap():
    res = sandbox("print('x' * 200_000)\nimport sys; print('E' * 50_000, file=sys.stderr)")
    assert res["truncated"] is True
    assert len(res["stdout"].encode()) + len(res["stderr"].encode()) <= 16 * 1024


@requires_runner
def test_code_over_20kb_rejected_by_runner_itself():
    """Bypass the client-side check: the runner must refuse before starting a container."""
    import time

    import aiohttp

    async def raw():
        conn = aiohttp.UnixConnector(path=client.socket_path())
        async with aiohttp.ClientSession(connector=conn) as s:
            t = time.monotonic()
            async with s.post("http://sandbox-runner/run", json={"code": "#" * (20 * 1024 + 1)}) as r:
                return r.status, await r.json(), time.monotonic() - t

    status, body, elapsed = run(raw())
    assert status == 413 and "20480" in body["detail"]
    assert elapsed < 1.0                                # no container was started


@requires_runner
def test_memory_limit_enforced():
    res = sandbox("b = bytearray(400 * 1024 * 1024)\nprint('allocated')", timeout=10)
    assert "allocated" not in res["stdout"]
    assert res["oom_killed"] or res["exit_code"] != 0
