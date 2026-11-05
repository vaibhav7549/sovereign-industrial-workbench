# Code sandbox: design and threat model

The agent's `run_python_sandboxed` tool and the Diagnostic Ping (`POST /dummy_tool`) run Python in
a throwaway container. The code is untrusted: an LLM writes it, and text inside a retrieved
document can steer that LLM (prompt injection).

```
backend (network_mode: host)                 sandbox-runner (network_mode: none)              Docker daemon (host, root)
  sandbox/client.py ──HTTP over /ipc/runner.sock──▶ app.py  POST /run, GET /health ──/var/run/docker.sock──▶ creates one container per run
        (sandbox-ipc volume, mounted only into these two services)                                  │
                                                                                                     ▼
                                                              sandbox container: python:3.11-slim, network none, read-only, uid 65534, ...
```

## Why a Unix socket and not an internal network

The backend uses `network_mode: host`, which the TLS layout relies on:
- Nginx reaches the backend at `127.0.0.1:8000`.
- The backend reaches Ollama and Atomic on the host's loopback.

A host-networked container cannot join a Docker network, including an `internal: true` one, and it cannot resolve service names. So `sandbox-runner` has **no network at all** (`network_mode: none`) and **no ports**. It listens only on `/ipc/runner.sock` in the `sandbox-ipc` named volume, which is mounted into `backend` and `sandbox-runner` and nothing else.

That is stricter than a shared network: there is no IP address, so nothing on the LAN or in another container can reach the runner. Only processes that can open that socket file can call it, which means the backend container plus root or members of the `docker` group on the host, who already control Docker anyway.

## What a sandbox run gets

Each `POST /run` creates a new container with the equivalent of:

```
docker run --rm --network none --read-only --memory 256m --memory-swap 256m --cpus 0.5 \
  --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --tmpfs /work:size=32m -w /work python:3.11-slim python -I -c "<code>"
```

| Control | Effect |
|---|---|
| `--network none` | Loopback only. No outbound connections, no DNS, no access to the LAN, Ollama, Atomic or the backend |
| `--read-only` + `/work` tmpfs 32 MB | Nothing outside `/work` is writable. `/work` is in RAM and disappears with the container |
| No bind mounts or volumes | No host path is visible: no Docker socket, no `/data` vault, no `.env`, no certificates. `/etc/passwd` inside is the image's own file, not the host's |
| `--user 65534:65534`, `--cap-drop ALL`, `no-new-privileges` | Runs as `nobody` with no capabilities and cannot gain any (setuid binaries do nothing) |
| `--memory 256m` (no swap), `--cpus 0.5`, `--pids-limit 64` | Limits memory, CPU and fork bombs |
| Hard timeout: default 5 s, capped at 10 s | The runner kills the container when the timeout expires |
| Output cap 16 KB (stdout + stderr) | Larger output is truncated; the host log file is limited to 1 MB per container |
| `--rm` | The container is force-removed after every run, including timeouts and errors. Leftovers from a crash (label `sovereign.sandbox=1`) are removed when the runner starts |
| Docker's default seccomp and AppArmor profiles | Still apply (the runner never disables them) |

Requests are checked **before** any container starts:
- Code is at most 20 KB (counted in UTF-8 bytes); over that the runner returns 413.
- The timeout must be a positive number; anything above 10 s is capped at 10.
- Only the fields `code` and `timeout` are accepted, and the whole body is at most 64 KB.
- At most 2 runs execute at once; others wait up to 30 s, then get 429.

Callers cannot choose the image, mounts, flags or user. Those are fixed in `sandbox-runner/sandbox_core.py`. The runner exposes only `POST /run` and `GET /health`; there are no docs or OpenAPI routes.

## The Docker socket: root-equivalent host access

**Mounting `/var/run/docker.sock` into `sandbox-runner` gives that container root-equivalent access to the host on rootful Docker.** Anyone who can send arbitrary requests to the Docker API can start a container with `--privileged` and `-v /:/host`, and from there read or change any file on the laptop: the encryption master key, the vault, the TLS CA key, SSH keys. The same holds for anyone in the host's `docker` group. Dropping capabilities or making the runner's filesystem read-only does not change this, because the power is in the API calls, not in the runner's own privileges.

So the runner is the most sensitive service in the stack. These measures keep it hard to reach and hard to misuse:
- **Only service with the socket.** `docker compose config | grep -n docker.sock` shows the socket under `sandbox-runner` only. The backend and the sandbox containers never get it.
- **Not on any network.** It has `network_mode: none` and no ports. The only way in is the socket file shared with the backend.
- **Fixed behaviour.** It sends exactly one container spec, built in code; request fields never reach Docker except as the `code` argument and the capped timeout.
- **Small and contained.** It is under 400 lines of Python (`app.py`, `sandbox_core.py`) on FastAPI, uvicorn and aiohttp, with a read-only root filesystem, `cap_drop: ALL`, `no-new-privileges` and a 16 MB `/tmp`.

**Why this is accepted for the demo.** The workbench runs on one laptop with one operator. To abuse the socket, an attacker first needs code execution in the backend or the runner. The backend already holds the decryption keys and the plaintext at the response boundary, so a backend compromise is already a full data compromise; the socket adds host-root on top of that. The code the agent writes runs in the sandbox, not in the runner, and has no network to call home.

**Not acceptable beyond a single-user demo.** Before multi-user or production use, pick at least one of:
- **Rootless Docker** or `userns-remap`, so "root" in the Docker API is not host root.
- **gVisor (`runsc`) or Kata** as the sandbox runtime, so a kernel bug in the sandbox doesn't become a host compromise.
- **A separate VM** for the runner and its containers.

Also pin `python:3.11-slim` by digest and keep it patched.

## Residual risks

- **Shared kernel.** A container is not a VM. A Linux kernel exploit from inside the sandbox could escape it; seccomp and dropped capabilities reduce, but don't remove, that risk.
- **Output goes back to the model and the operator.** The sandbox can't send anything over the network, but whatever it prints is shown in the answer. That only goes to the same user who asked.
- **Resource use while running.** A run can use half a CPU and 256 MB for up to 10 s, and two runs can execute at once.

## Operating it

```bash
docker pull python:3.11-slim                    # sandbox image (already present: the backend builds on it)
docker compose up -d --build backend sandbox-runner
docker compose config | grep -n "docker.sock"   # only under sandbox-runner
docker compose exec backend python -m pytest -q -rs tests/test_sandbox.py   # real isolation tests
docker ps -a --filter label=sovereign.sandbox=1 # should be empty when nothing is running
```

The Diagnostic Ping button in the UI calls `POST /dummy_tool`, which runs `print(1+1)` in the sandbox and reports the result.
