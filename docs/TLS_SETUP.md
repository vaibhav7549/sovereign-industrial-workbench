# TLS for the two-laptop demo

Browser ↔ server traffic is encrypted with TLS 1.2/1.3, so whoever runs the Wi-Fi or hotspot (or
the ISP behind it) sees only that Laptop B talks to Laptop A on port 443. They cannot see queries,
answers, uploaded PDFs or session tokens.

```
Laptop B (browser) ──HTTPS :443──▶ Nginx (Laptop A) ──HTTP, loopback only──▶ backend 127.0.0.1:8000
                    ──HTTP  :80 ──▶ 301 redirect to https://
```

- Nginx is the only listener on the LAN, on :80 (redirect only) and :443.
- The backend binds to `127.0.0.1:8000`, so `http://<LAN_IP>:8000` is closed to other machines.
- The browser calls the API at the relative path `/api/...` on the same origin. That means no mixed content and no CORS preflight.
- The certificate comes from a small local CA made by `scripts/gen_tls_cert.sh`. Laptop B trusts the CA once. When the hotspot gives Laptop A a new IP, re-run the script and nothing changes on Laptop B.
- The CA is name-constrained to `localhost` and private/loopback IP ranges. So even a leaked `ca.key` cannot be used to impersonate a public website to Laptop B.

> **Host networking.** Both containers use `network_mode: host`. Ollama (:11434) and the Atomic MCP server (:8080) listen on Laptop A's loopback, and a bridge network would make you expose them on `0.0.0.0` instead. This is Linux-only, which matches the Ubuntu target.

---

## 1. Laptop A (server)

```bash
# 1. Find the Wi-Fi / hotspot IP (the one Laptop B can reach)
hostname -I            # e.g. 192.168.1.42  (iPhone hotspot: 172.20.10.x, Android: 192.168.43.x / 10.x)

# 2. Make the certificates (writes certs/, git-ignored; also writes SERVER_LAN_IP to ./.env)
./scripts/gen_tls_cert.sh 192.168.1.42
#    local mode, one laptop only:   ./scripts/gen_tls_cert.sh

# 3. Start
docker compose up -d --build
docker compose logs frontend | grep tls     # "[tls] certificate found ..."

# 4. If ufw is on, open only 80 and 443 (not 8000)
sudo ufw status && sudo ufw allow 443/tcp && sudo ufw allow 80/tcp
```

When the LAN IP changes (a different Wi-Fi, or a hotspot restart):

```bash
./scripts/gen_tls_cert.sh <NEW_IP> && docker compose up -d   # re-reads ./.env and the new cert
```

Copy **only `certs/ca/ca.crt`** to Laptop B, by USB stick or `scp`. It is public. **`certs/ca/ca.key` never leaves Laptop A.** The script prints the CA's SHA-256 fingerprint; check it on Laptop B after importing:

```bash
openssl x509 -in ca.crt -noout -fingerprint -sha256
```

## 2. Trust the CA on the client

### Ubuntu

```bash
# System store (curl, wget, Python, most CLI tools)
sudo cp ca.crt /usr/local/share/ca-certificates/sovereign-workbench-ca.crt
sudo update-ca-certificates

# Chrome / Chromium / Brave (they use the NSS store, not the system store)
sudo apt install -y libnss3-tools
certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n "Sovereign Workbench Local CA" -i ca.crt
#   Snap Chromium uses its own profile:
#   certutil -d sql:$HOME/snap/chromium/current/.pki/nssdb -A -t "C,," -n "Sovereign Workbench Local CA" -i ca.crt
```

**Firefox** (including the Ubuntu snap): open Settings → Privacy & Security → Certificates → View Certificates… → Authorities → Import…. Choose `ca.crt` and tick **"Trust this CA to identify websites"**.

Restart the browser, then open `https://<LAN_IP>/`. You should see a padlock with no warning.

### Windows 10/11

PowerShell for the current user (no admin needed; Windows asks you to confirm):

```powershell
Import-Certificate -FilePath .\ca.crt -CertStoreLocation Cert:\CurrentUser\Root
#   or:  certutil -user -addstore Root ca.crt
```

The GUI alternative: double-click `ca.crt` → Install Certificate → Current User → "Place all certificates in the following store" → **Trusted Root Certification Authorities**.

Chrome and Edge use this store directly. Recent Firefox versions also read it (`security.enterprise_roots.enabled`, on by default). If Firefox still warns, import it as in the Ubuntu Firefox steps.

### Local mode (one laptop)

Run `./scripts/gen_tls_cert.sh` with no IP, then trust `certs/ca/ca.crt` on the same laptop using the Ubuntu steps above. Open `https://localhost/`.

### Remove trust after the demo

```bash
# Ubuntu
sudo rm /usr/local/share/ca-certificates/sovereign-workbench-ca.crt && sudo update-ca-certificates --fresh
certutil -d sql:$HOME/.pki/nssdb -D -n "Sovereign Workbench Local CA"
```

```powershell
# Windows
certutil -user -delstore Root "Sovereign Workbench Local CA"
```

---

## 3. Verify

Run these on Laptop B unless noted. Replace `192.168.1.42` with your IP.

```bash
IP=192.168.1.42

# TLS handshake and certificate (-k as specified; the --cacert form proves the chain and hostname are valid)
curl -vk https://$IP/ 2>&1 | grep -E "SSL connection|TLSv1|subject|issuer"
curl -sS --cacert ca.crt -o /dev/null -w "%{http_code}\n" https://$IP/          # 200

# API through the TLS proxy (/api is stripped; this is the backend's GET /)
curl -sS --cacert ca.crt https://$IP/api/

# Log in (username is a query parameter), then check the encryption layer over TLS
TOKEN=$(curl -sS --cacert ca.crt -X POST "https://$IP/api/login?username=operator.demo" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -sS --cacert ca.crt -X POST "https://$IP/api/agent/verify-encryption?token=$TOKEN"

# Port 80 only redirects
curl -sI http://$IP/ | grep -iE "^(HTTP|location)"                              # 301, https://...

# Security headers
curl -sI --cacert ca.crt https://$IP/ | grep -iE "strict-transport|content-security|x-frame|x-content-type|referrer"

# Protocols: 1.2 and 1.3 succeed, 1.1 and 1.0 are refused by the server
openssl s_client -connect $IP:443 -servername localhost -tls1_3 </dev/null 2>/dev/null | grep -E "^ *(Protocol|Cipher) *:"
openssl s_client -connect $IP:443 -servername localhost -tls1_2 </dev/null 2>/dev/null | grep -E "^ *(Protocol|Cipher) *:"
#   SECLEVEL=0 makes the *client* willing to try TLS 1.1, so the failure you see comes from the server:
openssl s_client -connect $IP:443 -tls1_1 -cipher 'DEFAULT@SECLEVEL=0' </dev/null 2>&1 | grep -iE "alert|error|no protocols"

# Backend is NOT reachable from the LAN
curl -m 5 http://$IP:8000/        # expect: "Connection refused" (or a timeout if ufw drops it)
```

On **Laptop A**, check what is listening:

```bash
ss -ltnp | grep -E ':(80|443|8000|8080|11434)\b'
#   expect 0.0.0.0:80, 0.0.0.0:443, 127.0.0.1:8000
#   127.0.0.1:11434 (Ollama) and 127.0.0.1:8080 (Atomic) should also be loopback-only. If either
#   shows 0.0.0.0, the LAN can reach the LLM or the knowledge graph directly, bypassing TLS.
docker compose exec frontend nginx -t       # config syntax check
```

Optional full scan from Laptop B: `sudo apt install nmap && nmap -Pn -p 80,443,8000,8080,11434 $IP`. Only 80 and 443 should be open.

---

## Notes

- **Swagger docs** (`/docs`) are not proxied. The page loads its JavaScript from a CDN, which the strict Content-Security-Policy blocks (and would be a third-party fetch anyway). Use `http://127.0.0.1:8000/docs` on Laptop A.
- **The CSP blocks third-party requests from the browser.** The UI currently pulls Google Fonts (`src/index.css`) and Google favicons (`App.tsx`). Both are blocked, so the UI falls back to system fonts and shows no favicons on paper cards. This is deliberate: favicon URLs carry the paper domain, which tells Google what was searched.
- **HSTS** is sent with `max-age=31536000`, without `includeSubDomains` or `preload`. Browsers ignore HSTS for bare IP addresses, so it applies only to `https://localhost`.
- **Bare-metal dev** (`npm run dev` plus `python main.py`) still works over plain HTTP on `localhost:5173`. Vite proxies `/api` to `127.0.0.1:8000`. That setup is for one machine only.
- **TLS ends at Nginx,** and the hop from Nginx to the backend is plain HTTP over loopback on the same host, so it never touches the network.
