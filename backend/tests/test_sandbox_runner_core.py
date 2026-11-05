"""Task 3: sandbox-runner core (validation, container flags, output cap, orchestration) and wiring.

Pure tests with a fake Docker; no daemon needed. They import sandbox-runner/ from the repo, so
they skip inside the backend container (which holds backend/ only), like the TLS tests.
The real-container tests are in test_sandbox.py.
"""

import asyncio
import os
import struct
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUNNER_DIR = os.path.join(REPO, "sandbox-runner")
if not os.path.isdir(RUNNER_DIR):
    pytest.skip("sandbox-runner/ not present (e.g. inside the backend container)", allow_module_level=True)
sys.path.insert(0, RUNNER_DIR)

import sandbox_core as core  # noqa: E402


def frame(stream, data):
    return bytes([stream, 0, 0, 0]) + struct.pack(">I", len(data)) + data


class FakeDocker:
    def __init__(self, image=True, exit_code=0, hang=False, logs=b"", fail_start=False):
        self.calls, self.image, self.exit_code, self.hang = [], image, exit_code, hang
        self.logs, self.fail_start = logs, fail_start

    async def image_exists(self, image):
        self.calls.append(("image_exists", image))
        return self.image

    async def create(self, name, spec):
        self.calls.append(("create", spec))
        return "cid1"

    async def start(self, cid):
        self.calls.append(("start", cid))
        if self.fail_start:
            raise RuntimeError("start failed")

    async def wait(self, cid):
        self.calls.append(("wait", cid))
        if self.hang:
            await asyncio.sleep(3600)
        return self.exit_code

    async def kill(self, cid):
        self.calls.append(("kill", cid))

    async def read_logs(self, cid, demux):
        self.calls.append(("logs", cid))
        demux.feed(self.logs)

    async def oom_killed(self, cid):
        return False

    async def remove(self, cid):
        self.calls.append(("remove", cid))

    def names(self):
        return [c[0] for c in self.calls]


# ----------------------------------------------------------------------------- validation
def test_code_over_20kb_rejected_before_any_docker_call():
    docker = FakeDocker()
    with pytest.raises(core.ValidationError) as e:
        core.validate_request({"code": "#" * (20 * 1024 + 1)})
    assert e.value.status == 413
    assert docker.calls == []        # validation runs before run_code(); app.py returns 413 here


def test_limit_is_bytes_not_characters():
    core.validate_request({"code": "#" * (20 * 1024)})                 # exactly 20 KB is fine
    with pytest.raises(core.ValidationError):
        core.validate_request({"code": "é" * (10 * 1024 + 1)})          # 2 bytes each in UTF-8


def test_timeout_capped_at_10s_and_defaulted():
    assert core.validate_request({"code": "1", "timeout": 999}).timeout_s == 10.0
    assert core.validate_request({"code": "1"}).timeout_s == core.DEFAULT_TIMEOUT_S


@pytest.mark.parametrize("body", [
    "print(1)", {"code": ""}, {"code": "  "}, {"code": 5}, {"code": "1", "timeout": 0},
    {"code": "1", "timeout": -1}, {"code": "1", "timeout": float("nan")}, {"code": "1", "timeout": True},
    {"code": "1", "timeout": "5"}, {"code": "1", "image": "alpine"}, {"code": "a\x00b"},
])
def test_bad_requests_rejected(body):
    with pytest.raises(core.ValidationError):
        core.validate_request(body)


# ----------------------------------------------------------------------------- container flags
def test_container_spec_matches_required_flags():
    spec = core.container_spec("print(1)")
    hc = spec["HostConfig"]
    assert spec["Image"] == "python:3.11-slim"
    assert spec["User"] == "65534:65534" and spec["WorkingDir"] == "/work"
    assert spec["NetworkDisabled"] is True and hc["NetworkMode"] == "none"                 # --network none
    assert hc["ReadonlyRootfs"] is True                                                    # --read-only
    assert hc["Memory"] == 256 * 1024 * 1024 and hc["MemorySwap"] == hc["Memory"]          # --memory 256m
    assert hc["NanoCpus"] == 500_000_000                                                   # --cpus 0.5
    assert hc["PidsLimit"] == 64                                                           # --pids-limit 64
    assert hc["CapDrop"] == ["ALL"]                                                        # --cap-drop ALL
    assert hc["SecurityOpt"] == ["no-new-privileges"]                                      # no-new-privileges
    assert "size=32m" in hc["Tmpfs"]["/work"]                                              # --tmpfs /work:size=32m
    assert hc["Privileged"] is False
    for forbidden in ("Binds", "Mounts", "Devices", "CapAdd", "PortBindings", "VolumesFrom"):
        assert forbidden not in hc, forbidden                                              # nothing from the host
    assert spec["Cmd"][:3] == ["python", "-I", "-c"] and spec["Cmd"][3] == "print(1)"


# ----------------------------------------------------------------------------- output cap
def test_logdemux_splits_streams_and_handles_partial_frames():
    d = core.LogDemux(cap=100)
    data = frame(1, b"out\n") + frame(2, b"err\n")
    for i in range(len(data)):          # one byte at a time
        d.feed(data[i:i + 1])
    assert d.result() == ("out\n", "err\n", False)


def test_logdemux_caps_total_output():
    d = core.LogDemux(cap=16 * 1024)
    d.feed(frame(1, b"x" * 10_000) + frame(2, b"y" * 10_000) + frame(1, b"z" * 10))
    out, err, truncated = d.result()
    assert truncated and len(out) + len(err) == 16 * 1024 and "z" not in out


# ----------------------------------------------------------------------------- orchestration
def run(coro):
    return asyncio.run(coro)


def test_normal_run_creates_starts_waits_reads_and_removes():
    docker = FakeDocker(logs=frame(1, b"2\n"))
    res = run(core.run_code(core.RunRequest("print(1+1)", 5), docker))
    assert docker.names() == ["image_exists", "create", "start", "wait", "logs", "remove"]
    assert res["exit_code"] == 0 and res["stdout"] == "2\n" and not res["timed_out"]


def test_timeout_kills_then_removes():
    docker = FakeDocker(hang=True)
    res = run(core.run_code(core.RunRequest("while True: pass", 0.2), docker))
    assert res["timed_out"] and res["exit_code"] is None
    assert docker.names()[-3:] == ["kill", "logs", "remove"]


def test_container_removed_even_when_start_fails():
    docker = FakeDocker(fail_start=True)
    with pytest.raises(RuntimeError):
        run(core.run_code(core.RunRequest("1", 5), docker))
    assert docker.names()[-1] == "remove"


def test_missing_image_is_unavailable_and_creates_nothing():
    docker = FakeDocker(image=False)
    with pytest.raises(core.SandboxUnavailable, match="docker pull python:3.11-slim"):
        run(core.run_code(core.RunRequest("1", 5), docker))
    assert "create" not in docker.names()


# ----------------------------------------------------------------------------- HTTP surface
def test_runner_http_surface_only_run_and_health(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("aiohttp")
    pytest.importorskip("httpx")
    import app as runner_app
    from fastapi.testclient import TestClient

    docker = FakeDocker(logs=frame(1, b"2\n"))

    async def sweep():
        return 0

    docker.sweep = sweep
    monkeypatch.setattr(runner_app, "docker", docker)
    with TestClient(runner_app.app) as c:
        r = c.post("/run", json={"code": "#" * (20 * 1024 + 1)})
        assert r.status_code == 413 and docker.calls == []       # rejected before Docker is touched
        assert c.post("/run", content=b"x" * (65 * 1024)).status_code == 413
        assert c.post("/run", content=b"not json").status_code == 400
        assert c.post("/run", json={"code": "print(1+1)"}).json()["stdout"] == "2\n"
        assert c.get("/health").json()["image_present"] is True
        for path in ("/docs", "/openapi.json", "/redoc", "/containers/json", "/"):
            assert c.get(path).status_code == 404, path
        assert c.get("/run").status_code == 405


# ----------------------------------------------------------------------------- compose wiring
def test_compose_socket_only_in_runner_and_runner_unreachable_by_network():
    yaml = pytest.importorskip("yaml")
    for name in ("docker-compose.yml", "docker-compose.yml.example"):
        path = os.path.join(REPO, name)
        if not os.path.exists(path):
            continue
        services = yaml.safe_load(open(path))["services"]
        with_sock = [s for s, cfg in services.items()
                     if any("docker.sock" in str(v) for v in cfg.get("volumes", []))]
        assert with_sock == ["sandbox-runner"], name
        runner = services["sandbox-runner"]
        assert runner["network_mode"] == "none" and "ports" not in runner and "networks" not in runner
        assert "sandbox-ipc:/ipc" in services["backend"]["volumes"]
        assert services["backend"]["network_mode"] == "host"        # TLS layout unchanged
