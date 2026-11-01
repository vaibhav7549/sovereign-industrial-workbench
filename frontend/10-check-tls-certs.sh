#!/bin/sh
# Runs from the nginx image's /docker-entrypoint.d/ before Nginx starts.
# Fails fast with a readable message instead of Nginx's "cannot load certificate".
set -eu
for f in /etc/nginx/certs/server.crt /etc/nginx/certs/server.key; do
    if [ ! -s "$f" ]; then
        echo "[tls] $f is missing." >&2
        echo "[tls] On the host run:  ./scripts/gen_tls_cert.sh <LAN_IP>   (or with no IP for local mode)" >&2
        echo "[tls] then:             docker compose up -d" >&2
        exit 1
    fi
done
echo "[tls] certificate found at /etc/nginx/certs/server.crt"
