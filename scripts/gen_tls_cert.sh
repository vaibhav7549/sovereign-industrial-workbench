#!/usr/bin/env bash
# Generate TLS material for the Nginx front door (Task 1).
#
#   scripts/gen_tls_cert.sh <LAN_IP>      # remote mode: localhost + 127.0.0.1 + <LAN_IP>
#   scripts/gen_tls_cert.sh               # local mode:  localhost + 127.0.0.1 only
#   scripts/gen_tls_cert.sh <LAN_IP> --new-ca   # also replace the local CA
#
# Layout (all under certs/, git-ignored, directories 700, keys 600):
#   certs/ca/ca.crt          -> copy THIS to the client laptop and trust it (public, safe to copy)
#   certs/ca/ca.key          -> never leaves this machine; whoever has it can impersonate the server
#   certs/server/server.crt  -> mounted read-only into the Nginx container
#   certs/server/server.key
#
# Why a local CA instead of one self-signed leaf: the client trusts the CA once, and when the
# hotspot hands out a new LAN IP you only re-run this script; nothing changes on the client.
# The CA carries critical nameConstraints (localhost + private/loopback IP ranges only), so even
# if ca.key leaked it could not be used to impersonate public sites to a client that trusts it.
set -euo pipefail

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

LAN_IP=""
NEW_CA=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage 0 ;;
    --new-ca) NEW_CA=1 ;;
    -*) echo "unknown option: $arg" >&2; usage 1 ;;
    *) [ -z "$LAN_IP" ] || { echo "only one LAN IP is supported" >&2; exit 1; }; LAN_IP="$arg" ;;
  esac
done

command -v openssl >/dev/null || { echo "openssl not found (sudo apt install openssl)" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${CERT_DIR:-$ROOT/certs}"
CA_DIR="$CERT_DIR/ca"
SRV_DIR="$CERT_DIR/server"
CA_DAYS="${CA_DAYS:-1825}"
SERVER_DAYS="${SERVER_DAYS:-397}"

# ---- validate the LAN IP: dotted IPv4 inside a range the CA is allowed to sign ----------------
if [ -n "$LAN_IP" ]; then
  if ! [[ "$LAN_IP" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
    echo "error: '$LAN_IP' is not an IPv4 address (find yours with: hostname -I)" >&2; exit 1
  fi
  o1=${BASH_REMATCH[1]}; o2=${BASH_REMATCH[2]}; o3=${BASH_REMATCH[3]}; o4=${BASH_REMATCH[4]}
  for o in "$o1" "$o2" "$o3" "$o4"; do
    [ "$o" -le 255 ] || { echo "error: '$LAN_IP' has an octet > 255" >&2; exit 1; }
  done
  private=0
  if [ "$o1" -eq 10 ] || [ "$o1" -eq 127 ]; then private=1; fi
  if [ "$o1" -eq 172 ] && [ "$o2" -ge 16 ] && [ "$o2" -le 31 ]; then private=1; fi
  if [ "$o1" -eq 192 ] && [ "$o2" -eq 168 ]; then private=1; fi
  if [ "$o1" -eq 169 ] && [ "$o2" -eq 254 ]; then private=1; fi
  if [ "$o1" -eq 100 ] && [ "$o2" -ge 64 ] && [ "$o2" -le 127 ]; then private=1; fi
  if [ "$private" -ne 1 ]; then
    echo "error: $LAN_IP is a public address. This CA only signs localhost and private LAN ranges" >&2
    echo "       (10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10). Use the Wi-Fi/hotspot IP." >&2
    exit 1
  fi
fi

umask 077
mkdir -p "$CA_DIR" "$SRV_DIR"
chmod 700 "$CERT_DIR" "$CA_DIR" "$SRV_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---- 1. local CA (created once, reused) -----------------------------------------------------------
if [ "$NEW_CA" -eq 1 ] || [ ! -s "$CA_DIR/ca.key" ] || [ ! -s "$CA_DIR/ca.crt" ]; then
  cat > "$TMP/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
prompt = no
x509_extensions = v3_ca
[dn]
CN = Sovereign Workbench Local CA
O = Sovereign Workbench (demo, not publicly trusted)
[v3_ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
nameConstraints = critical, permitted;DNS:localhost, permitted;IP:127.0.0.0/255.0.0.0, permitted;IP:10.0.0.0/255.0.0.0, permitted;IP:172.16.0.0/255.240.0.0, permitted;IP:192.168.0.0/255.255.0.0, permitted;IP:169.254.0.0/255.255.0.0, permitted;IP:100.64.0.0/255.192.0.0
EOF
  openssl ecparam -name prime256v1 -genkey -noout -out "$CA_DIR/ca.key"
  openssl req -x509 -new -sha256 -days "$CA_DAYS" -key "$CA_DIR/ca.key" \
    -config "$TMP/ca.cnf" -out "$CA_DIR/ca.crt"
  echo "created new local CA: $CA_DIR/ca.crt"
  NEW_CA=1
else
  echo "reusing existing local CA: $CA_DIR/ca.crt"
fi

# ---- 2. server certificate for this LAN IP --------------------------------------------------------
SAN="DNS:localhost, IP:127.0.0.1"
[ -n "$LAN_IP" ] && SAN="$SAN, IP:$LAN_IP"
cat > "$TMP/server.ext" <<EOF
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
subjectAltName = $SAN
EOF
openssl ecparam -name prime256v1 -genkey -noout -out "$TMP/server.key"
openssl req -new -sha256 -key "$TMP/server.key" -subj "/CN=Sovereign Workbench/O=Sovereign Workbench" \
  -out "$TMP/server.csr"
openssl x509 -req -sha256 -days "$SERVER_DAYS" -in "$TMP/server.csr" \
  -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" -set_serial "0x$(openssl rand -hex 16)" \
  -extfile "$TMP/server.ext" -out "$TMP/server.crt" 2>/dev/null
openssl verify -CAfile "$CA_DIR/ca.crt" "$TMP/server.crt" >/dev/null

# Nginx needs the full chain? No: the client trusts the CA directly, so the leaf alone is enough.
mv -f "$TMP/server.key" "$SRV_DIR/server.key"
mv -f "$TMP/server.crt" "$SRV_DIR/server.crt"
chmod 600 "$CA_DIR/ca.key" "$SRV_DIR/server.key"
chmod 644 "$CA_DIR/ca.crt" "$SRV_DIR/server.crt"

# ---- 3. record the LAN IP for docker compose (root .env, git-ignored; backend/.env is untouched) ---
ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then grep -v '^SERVER_LAN_IP=' "$ENV_FILE" > "$TMP/env" || true; else : > "$TMP/env"; fi
echo "SERVER_LAN_IP=$LAN_IP" >> "$TMP/env"
cat "$TMP/env" > "$ENV_FILE"

FP="$(openssl x509 -in "$CA_DIR/ca.crt" -noout -fingerprint -sha256 | cut -d= -f2)"
echo
echo "server certificate: $SRV_DIR/server.crt  (SAN: $SAN, valid $SERVER_DAYS days)"
echo "SERVER_LAN_IP=$LAN_IP written to $ENV_FILE"
echo "CA SHA-256 fingerprint (check it on the client after importing):"
echo "  $FP"
echo
echo "next:"
echo "  docker compose up -d --build        # or: docker compose restart frontend"
if [ "$NEW_CA" -eq 1 ]; then
  echo "  copy certs/ca/ca.crt (NOT ca.key) to the client laptop and trust it - see docs/TLS_SETUP.md"
fi
if [ -n "$LAN_IP" ]; then echo "  open https://$LAN_IP/ on the client"; else echo "  open https://localhost/"; fi
