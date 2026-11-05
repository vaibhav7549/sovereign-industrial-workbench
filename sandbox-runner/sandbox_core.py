"""Sandbox runner core: limits, input validation, container spec, log demux, run orchestration.

Pure standard library so it can be unit-tested without Docker, FastAPI or aiohttp. app.py plugs
in the real Docker Engine API client (DockerAPI) and the HTTP endpoints.

Every run gets a fresh container equivalent to:

  docker run --rm --network none --read-only --memory 256m --memory-swap 256m --cpus 0.5
             --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges --user 65534:65534
             --tmpfs /work:size=32m -w /work python:3.11-slim python -I -c <code>

with a hard wall-clock timeout after which the container is killed. "--rm" is done explicitly
(force-remove in a finally block) so the output can be read after exit and removal still
happens on every path, including timeouts and errors.
"""

from __future__ import annotations

import asyncio
import os
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple

# ---- hard limits (policy: callers cannot raise these) -------------------------------------
MAX_CODE_BYTES = 20 * 1024
MAX_TIMEOUT_S = 10.0
DEFAULT_TIMEOUT_S = 5.0
MAX_OUTPUT_BYTES = 16 * 1024          # stdout + stderr together
MAX_REQUEST_BYTES = 64 * 1024         # whole JSON body, checked before parsing

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.11-slim")
SANDBOX_LABEL = "sovereign.sandbox"
SANDBOX_USER = "65534:65534"          # nobody:nogroup
MEMORY_BYTES = 256 * 1024 * 1024
NANO_CPUS = 500_000_000               # 0.5 CPU
PIDS_LIMIT = 64
WORKDIR = "/work"
WORKDIR_TMPFS = "rw,nosuid,nodev,size=32m,mode=1777"
KILL_GRACE_S = 5.0                    # time allowed for kill + log read after the timeout


class ValidationError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class RunRequest:
    code: str
    timeout_s: float


def validate_request(body: Any) -> RunRequest:
    """Check a decoded JSON body. Raises ValidationError before anything touches Docker."""
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    unknown = set(body) - {"code", "timeout"}
    if unknown:
        raise ValidationError(f"unknown field(s): {sorted(unknown)}")
    code = body.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValidationError("'code' must be a non-empty string")
    if "\x00" in code:
        raise ValidationError("'code' must not contain NUL bytes")
    size = len(code.encode("utf-8"))
    if size > MAX_CODE_BYTES:
        raise ValidationError(f"code is {size} bytes; the limit is {MAX_CODE_BYTES}", status=413)
    timeout = body.get("timeout", DEFAULT_TIMEOUT_S)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValidationError("'timeout' must be a number of seconds")
    if not timeout > 0:   # also rejects NaN
        raise ValidationError("'timeout' must be > 0")
    return RunRequest(code=code, timeout_s=min(float(timeout), MAX_TIMEOUT_S))


def container_spec(code: str, image: str = SANDBOX_IMAGE) -> Dict[str, Any]:
    """Docker Engine API body for POST /containers/create."""
    return {
        "Image": image,
        "Cmd": ["python", "-I", "-c", code],
        "WorkingDir": WORKDIR,
        "User": SANDBOX_USER,
        "Env": ["HOME=/work", "TMPDIR=/work", "PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1"],
        "NetworkDisabled": True,
        "AttachStdin": False, "AttachStdout": False, "AttachStderr": False,
        "OpenStdin": False, "Tty": False,
        "Labels": {SANDBOX_LABEL: "1"},
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Memory": MEMORY_BYTES,
            "MemorySwap": MEMORY_BYTES,          # no swap on top of the memory limit
            "NanoCpus": NANO_CPUS,
            "PidsLimit": PIDS_LIMIT,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {WORKDIR: WORKDIR_TMPFS},
            "Privileged": False,
            "AutoRemove": False,                 # removed explicitly after the output is read
            "IpcMode": "private",
            # Bounded log file on the host, so a print loop cannot fill the disk.
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "1m", "max-file": "1"}},
        },
    }


class LogDemux:
    """Decode Docker's multiplexed log stream (8-byte frame headers) up to a byte cap."""

    def __init__(self, cap: int = MAX_OUTPUT_BYTES):
        self.cap = cap
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.truncated = False
        self._buf = bytearray()

    @property
    def total(self) -> int:
        return len(self.stdout) + len(self.stderr)

    @property
    def full(self) -> bool:
        return self.truncated

    def feed(self, data: bytes) -> None:
        if self.truncated:
            return
        self._buf.extend(data)
        while len(self._buf) >= 8:
            stream, size = self._buf[0], struct.unpack(">I", bytes(self._buf[4:8]))[0]
            if len(self._buf) < 8 + size:
                return
            payload = bytes(self._buf[8:8 + size])
            del self._buf[:8 + size]
            room = self.cap - self.total
            if len(payload) > room:
                payload, self.truncated = payload[:room], True
            (self.stderr if stream == 2 else self.stdout).extend(payload)
            if self.truncated:
                self._buf.clear()
                return

    def result(self) -> Tuple[str, str, bool]:
        return (self.stdout.decode("utf-8", "replace"), self.stderr.decode("utf-8", "replace"), self.truncated)


class Docker(Protocol):
    async def image_exists(self, image: str) -> bool: ...
    async def create(self, name: str, spec: Dict[str, Any]) -> str: ...
    async def start(self, cid: str) -> None: ...
    async def wait(self, cid: str) -> int: ...
    async def kill(self, cid: str) -> None: ...
    async def read_logs(self, cid: str, demux: LogDemux) -> None: ...
    async def oom_killed(self, cid: str) -> bool: ...
    async def remove(self, cid: str) -> None: ...


class SandboxUnavailable(RuntimeError):
    """Docker or the sandbox image is not available (HTTP 503)."""


async def run_code(req: RunRequest, docker: Docker, image: str = SANDBOX_IMAGE) -> Dict[str, Any]:
    """Run one request in a fresh container and always remove it."""
    if not await docker.image_exists(image):
        raise SandboxUnavailable(f"sandbox image {image!r} is not present; run: docker pull {image}")
    name = f"sbx-{uuid.uuid4().hex[:12]}"
    cid: Optional[str] = None
    started = time.monotonic()
    try:
        cid = await docker.create(name, container_spec(req.code, image))
        await docker.start(cid)
        timed_out = False
        exit_code: Optional[int]
        try:
            exit_code = await asyncio.wait_for(docker.wait(cid), timeout=req.timeout_s)
        except asyncio.TimeoutError:
            timed_out = True
            exit_code = None
            try:
                await docker.kill(cid)
            except Exception:
                pass  # it may have exited in the meantime; remove(force) below stops it regardless
        demux = LogDemux()
        try:
            await asyncio.wait_for(docker.read_logs(cid, demux), timeout=KILL_GRACE_S)
        except asyncio.TimeoutError:
            demux.truncated = True
        stdout, stderr, truncated = demux.result()
        oom = await docker.oom_killed(cid) if not timed_out else False
        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "truncated": truncated,
            "oom_killed": oom,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "limits": {"timeout_s": req.timeout_s, "memory_mb": MEMORY_BYTES // (1024 * 1024), "cpus": 0.5,
                       "pids": PIDS_LIMIT, "output_bytes": MAX_OUTPUT_BYTES, "network": "none"},
        }
    finally:
        if cid is not None:
            try:
                await docker.remove(cid)
            except Exception:
                pass  # the startup sweep removes anything left behind (label sovereign.sandbox)
