# sandbox-runner: starts throwaway sandbox containers through the Docker socket.
# The ONLY service with /var/run/docker.sock mounted. See docs/SANDBOX.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The same packages the backend already uses. No Docker CLI or Docker SDK: the runner calls the
# Docker Engine API over the Unix socket with aiohttp.
RUN pip install --no-cache-dir fastapi uvicorn aiohttp

WORKDIR /app
COPY sandbox_core.py app.py ./

# Listens on a Unix socket in the shared sandbox-ipc volume; there is no TCP listener.
CMD ["sh", "-c", "rm -f /ipc/runner.sock && exec uvicorn app:app --uds /ipc/runner.sock"]
