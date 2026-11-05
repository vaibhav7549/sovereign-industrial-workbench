"""sandbox-runner: the only service with the Docker socket. Exposes exactly two routes.

  POST /run     {"code": "<python>", "timeout": <seconds, optional>}  -> run result
  GET  /health  -> Docker reachable? sandbox image present?

It listens on a Unix socket (/ipc/runner.sock) in a volume shared only with the backend. The
container itself has network_mode: none and publishes no ports (docker-compose.yml). Docker is
driven through the Engine API over /var/run/docker.sock with aiohttp; no Docker CLI or SDK.
Threat model: docs/SANDBOX.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict
from urllib.parse import quote

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sandbox_core import (MAX_REQUEST_BYTES, SANDBOX_IMAGE, SANDBOX_LABEL, LogDemux, SandboxUnavailable,
                          ValidationError, run_code, validate_request)

log = logging.getLogger("sandbox-runner")
DOCKER_SOCK = os.getenv("DOCKER_SOCK", "/var/run/docker.sock")
MAX_CONCURRENT = int(os.getenv("SANDBOX_MAX_CONCURRENT", "2"))
QUEUE_WAIT_S = 30.0


class DockerError(RuntimeError):
    pass


class DockerAPI:
    """Minimal Docker Engine API client over the Unix socket."""

    def __init__(self, sock: str = DOCKER_SOCK):
        self.sock = sock
        self._session: aiohttp.ClientSession | None = None

    def _s(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.UnixConnector(path=self.sock),
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=5),
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()

    async def _json(self, method: str, path: str, ok=(200,), **kw) -> Any:
        async with self._s().request(method, "http://docker" + path, **kw) as r:
            if r.status not in ok:
                raise DockerError(f"{method} {path.split('?')[0]} -> HTTP {r.status}: {(await r.text())[:200]}")
            return await r.json() if r.content_type == "application/json" else None

    async def image_exists(self, image: str) -> bool:
        async with self._s().get(f"http://docker/images/{quote(image, safe=':/@')}/json") as r:
            if r.status == 404:
                return False
            if r.status != 200:
                raise DockerError(f"image inspect -> HTTP {r.status}")
            return True

    async def create(self, name: str, spec: Dict[str, Any]) -> str:
        return (await self._json("POST", f"/containers/create?name={name}", ok=(201,), json=spec))["Id"]

    async def start(self, cid: str) -> None:
        await self._json("POST", f"/containers/{cid}/start", ok=(204, 304))

    async def wait(self, cid: str) -> int:
        return int((await self._json("POST", f"/containers/{cid}/wait"))["StatusCode"])

    async def kill(self, cid: str) -> None:
        await self._json("POST", f"/containers/{cid}/kill", ok=(204, 409))   # 409: already stopped

    async def read_logs(self, cid: str, demux: LogDemux) -> None:
        async with self._s().get(f"http://docker/containers/{cid}/logs?stdout=1&stderr=1") as r:
            if r.status != 200:
                raise DockerError(f"logs -> HTTP {r.status}")
            async for chunk in r.content.iter_chunked(4096):
                demux.feed(chunk)
                if demux.full:
                    break

    async def oom_killed(self, cid: str) -> bool:
        info = await self._json("GET", f"/containers/{cid}/json")
        return bool(info.get("State", {}).get("OOMKilled"))

    async def remove(self, cid: str) -> None:
        await self._json("DELETE", f"/containers/{cid}?force=1&v=1", ok=(204, 404))

    async def sweep(self) -> int:
        """Remove sandbox containers left over from a crash (label sovereign.sandbox=1)."""
        filters = quote(json.dumps({"label": [f"{SANDBOX_LABEL}=1"]}))
        leftovers = await self._json("GET", f"/containers/json?all=1&filters={filters}")
        for c in leftovers or []:
            await self.remove(c["Id"])
        return len(leftovers or [])


docker = DockerAPI()
_slots = asyncio.Semaphore(MAX_CONCURRENT)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        n = await docker.sweep()
        if n:
            log.warning("removed %d leftover sandbox container(s)", n)
    except Exception as e:  # Docker not reachable yet: /health reports it
        log.error("startup sweep failed: %s", type(e).__name__)
    yield
    await docker.close()


# No docs/OpenAPI routes: the only routes are /run and /health.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


@app.get("/health")
async def health():
    try:
        present = await docker.image_exists(SANDBOX_IMAGE)
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "docker": False,
                                                      "error": type(e).__name__})
    return {"status": "ok" if present else "degraded", "docker": True, "image": SANDBOX_IMAGE,
            "image_present": present}


@app.post("/run")
async def run(request: Request):
    # 1. Size check on the raw body, before JSON parsing and long before Docker.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        return _error(413, f"request body over {MAX_REQUEST_BYTES} bytes")
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > MAX_REQUEST_BYTES:
            return _error(413, f"request body over {MAX_REQUEST_BYTES} bytes")
    try:
        data = json.loads(bytes(body))
    except ValueError:
        return _error(400, "body is not valid JSON")
    # 2. Field validation (code <= 20 KB, timeout capped at 10 s).
    try:
        req = validate_request(data)
    except ValidationError as e:
        return _error(e.status, str(e))
    # 3. Bounded concurrency, then a throwaway container.
    try:
        await asyncio.wait_for(_slots.acquire(), timeout=QUEUE_WAIT_S)
    except asyncio.TimeoutError:
        return _error(429, "sandbox busy, try again")
    try:
        return await run_code(req, docker)
    except SandboxUnavailable as e:
        return _error(503, str(e))
    except Exception as e:
        log.error("run failed: %s: %s", type(e).__name__, e)
        return _error(500, f"sandbox error ({type(e).__name__})")
    finally:
        _slots.release()
