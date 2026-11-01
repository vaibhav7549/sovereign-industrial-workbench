"""Task 1: TLS certificate script, Nginx config and compose exposure checks.

The certificate tests run the real scripts/gen_tls_cert.sh (needs bash + openssl) in a temporary
copy of the repo layout, so nothing is written to the working tree. The Nginx/compose tests are
static guards; the live checks (curl / openssl s_client / port scan) are in docs/TLS_SETUP.md.
"""

import os
import re
import shutil
import socket
import ssl
import stat
import subprocess
import threading

import pytest

from cors_config import DEFAULT_ORIGINS, allowed_origins

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(REPO, "scripts", "gen_tls_cert.sh")

needs_openssl = pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("openssl") and os.path.exists(SCRIPT)),
    reason="bash, openssl and scripts/gen_tls_cert.sh required (run from the repo, not the container)",
)
needs_repo = pytest.mark.skipif(
    not os.path.exists(os.path.join(REPO, "frontend", "nginx.conf")),
    reason="frontend/ not present (e.g. inside the backend container, which holds backend/ only)",
)


def _run_script(root, *args):
    return subprocess.run(["bash", os.path.join(root, "scripts", "gen_tls_cert.sh"), *args],
                          capture_output=True, text=True, timeout=60)


def _openssl(*args):
    return subprocess.run(["openssl", *args], capture_output=True, text=True, timeout=30)


@pytest.fixture
def tls_root(tmp_path):
    """A throwaway repo root containing only scripts/gen_tls_cert.sh."""
    os.makedirs(tmp_path / "scripts")
    shutil.copy(SCRIPT, tmp_path / "scripts" / "gen_tls_cert.sh")
    return str(tmp_path)


def _fingerprint(path):
    return _openssl("x509", "-in", path, "-noout", "-fingerprint", "-sha256").stdout.strip()


# ------------------------------------------------------------------ certificate script
@needs_openssl
def test_cert_has_sans_chain_and_private_key_modes(tls_root):
    r = _run_script(tls_root, "192.168.1.42")
    assert r.returncode == 0, r.stderr
    certs = os.path.join(tls_root, "certs")
    srv_crt = os.path.join(certs, "server", "server.crt")
    srv_key = os.path.join(certs, "server", "server.key")
    ca_crt = os.path.join(certs, "ca", "ca.crt")
    ca_key = os.path.join(certs, "ca", "ca.key")

    text = _openssl("x509", "-in", srv_crt, "-noout", "-text").stdout
    assert "DNS:localhost" in text
    assert "IP Address:127.0.0.1" in text
    assert "IP Address:192.168.1.42" in text
    assert "TLS Web Server Authentication" in text
    assert "CA:FALSE" in text

    assert _openssl("verify", "-CAfile", ca_crt, srv_crt).returncode == 0
    for key in (srv_key, ca_key):
        assert stat.S_IMODE(os.stat(key).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(certs).st_mode) == 0o700
    with open(os.path.join(tls_root, ".env")) as f:
        assert "SERVER_LAN_IP=192.168.1.42" in f.read()


@needs_openssl
def test_local_mode_without_lan_ip(tls_root):
    r = _run_script(tls_root)
    assert r.returncode == 0, r.stderr
    text = _openssl("x509", "-in", os.path.join(tls_root, "certs", "server", "server.crt"),
                    "-noout", "-ext", "subjectAltName").stdout
    assert "DNS:localhost" in text and "IP Address:127.0.0.1" in text
    assert text.count("IP Address:") == 1


@needs_openssl
@pytest.mark.parametrize("bad", ["8.8.8.8", "999.1.1.1", "not-an-ip", "192.168.1"])
def test_public_or_malformed_ip_is_rejected(tls_root, bad):
    r = _run_script(tls_root, bad)
    assert r.returncode != 0
    assert not os.path.exists(os.path.join(tls_root, "certs", "server", "server.crt"))


@needs_openssl
def test_new_lan_ip_reuses_ca_so_client_need_not_retrust(tls_root):
    assert _run_script(tls_root, "192.168.1.42").returncode == 0
    ca = os.path.join(tls_root, "certs", "ca", "ca.crt")
    before = _fingerprint(ca)
    assert _run_script(tls_root, "172.20.10.3").returncode == 0  # e.g. iPhone hotspot
    assert _fingerprint(ca) == before
    san = _openssl("x509", "-in", os.path.join(tls_root, "certs", "server", "server.crt"),
                   "-noout", "-ext", "subjectAltName").stdout
    assert "172.20.10.3" in san and "192.168.1.42" not in san


@needs_openssl
def test_ca_name_constraints_block_public_names(tls_root, tmp_path):
    """Even with ca.key, a cert for a public site must fail verification against this CA."""
    assert _run_script(tls_root, "192.168.1.42").returncode == 0
    ca_crt = os.path.join(tls_root, "certs", "ca", "ca.crt")
    ca_key = os.path.join(tls_root, "certs", "ca", "ca.key")
    key, csr, crt, ext = (str(tmp_path / n) for n in ("evil.key", "evil.csr", "evil.crt", "evil.ext"))
    with open(ext, "w") as f:
        f.write("basicConstraints=CA:FALSE\nsubjectAltName=DNS:www.google.com, IP:8.8.8.8\n")
    assert _openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", key).returncode == 0
    assert _openssl("req", "-new", "-key", key, "-subj", "/CN=evil", "-out", csr).returncode == 0
    assert _openssl("x509", "-req", "-in", csr, "-CA", ca_crt, "-CAkey", ca_key, "-set_serial", "7",
                    "-days", "1", "-extfile", ext, "-out", crt).returncode == 0
    v = _openssl("verify", "-CAfile", ca_crt, crt)
    assert v.returncode != 0
    assert "permitted subtree violation" in (v.stdout + v.stderr)


@needs_openssl
@pytest.mark.parametrize("server_hostname", ["localhost", "127.0.0.1"])
def test_tls_handshake_verifies_hostname_with_trusted_ca(tls_root, server_hostname):
    """A client that trusts only ca.crt completes a verified TLS 1.2+ handshake."""
    assert _run_script(tls_root, "192.168.1.42").returncode == 0
    certs = os.path.join(tls_root, "certs")

    srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    srv_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    srv_ctx.load_cert_chain(os.path.join(certs, "server", "server.crt"),
                            os.path.join(certs, "server", "server.key"))
    lsock = socket.create_server(("127.0.0.1", 0))
    port = lsock.getsockname()[1]

    def serve():
        conn, _ = lsock.accept()
        try:
            with srv_ctx.wrap_socket(conn, server_side=True) as s:
                s.sendall(b"ok")
        except ssl.SSLError:
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    cli_ctx = ssl.create_default_context(cafile=os.path.join(certs, "ca", "ca.crt"))
    with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
        with cli_ctx.wrap_socket(raw, server_hostname=server_hostname) as s:
            assert s.version() in ("TLSv1.2", "TLSv1.3")
            assert s.recv(2) == b"ok"
    t.join(5)
    lsock.close()


@needs_openssl
def test_handshake_fails_for_name_not_in_cert(tls_root):
    assert _run_script(tls_root, "192.168.1.42").returncode == 0
    certs = os.path.join(tls_root, "certs")
    srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    srv_ctx.load_cert_chain(os.path.join(certs, "server", "server.crt"),
                            os.path.join(certs, "server", "server.key"))
    lsock = socket.create_server(("127.0.0.1", 0))
    port = lsock.getsockname()[1]

    def serve():
        conn, _ = lsock.accept()
        try:
            srv_ctx.wrap_socket(conn, server_side=True).close()
        except (ssl.SSLError, OSError):
            pass

    threading.Thread(target=serve, daemon=True).start()
    cli_ctx = ssl.create_default_context(cafile=os.path.join(certs, "ca", "ca.crt"))
    with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
        with pytest.raises(ssl.SSLCertVerificationError):
            cli_ctx.wrap_socket(raw, server_hostname="10.9.9.9")
    lsock.close()


# ------------------------------------------------------------------ static config guards
def _read(*parts):
    with open(os.path.join(REPO, *parts)) as f:
        return f.read()


def _strip_comments(text):
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


@needs_repo
def test_nginx_tls_policy_and_headers():
    conf = _strip_comments(_read("frontend", "nginx.conf"))
    assert re.search(r"ssl_protocols\s+TLSv1\.2\s+TLSv1\.3\s*;", conf)
    assert "return 301 https://$host$request_uri" in conf
    assert re.search(r"listen\s+443\s+ssl", conf)
    assert "proxy_pass http://127.0.0.1:8000/;" in conf
    for header in ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options",
                   "Referrer-Policy", "Content-Security-Policy", "Permissions-Policy"):
        assert f"add_header {header}" in conf, header
    # Any add_header inside a location block would silently drop the server-level headers.
    for block in re.findall(r"location[^{]*\{([^}]*)\}", conf):
        assert "add_header" not in block
    # No legacy protocols or weak cipher families.
    assert not re.search(r"TLSv1(\.0|\.1)?\b(?!\.[23])", conf.replace("TLSv1.2", "").replace("TLSv1.3", ""))
    ciphers = re.search(r"ssl_ciphers\s+([^;]+);", conf).group(1)
    for weak in ("RC4", "3DES", "MD5", "NULL", "EXPORT", "CBC", "DES-"):
        assert weak not in ciphers


@needs_repo
@pytest.mark.parametrize("compose", ["docker-compose.yml", "docker-compose.yml.example"])
def test_compose_publishes_only_nginx(compose):
    path = os.path.join(REPO, compose)
    if not os.path.exists(path):
        pytest.skip(f"{compose} not present")
    text = _strip_comments(_read(compose))
    assert "- HOST=127.0.0.1" in text            # backend on loopback under host networking
    assert "8000:8000" not in text and "ports:" not in text
    assert "./certs/server:/etc/nginx/certs:ro" in text
    assert "ca.key" not in text and "certs/ca" not in text
    assert "VITE_API_URL=/api" in text


@needs_repo
def test_frontend_uses_relative_api_path():
    app = _read("frontend", "src", "App.tsx")
    assert 'import.meta.env.VITE_API_URL || "/api"' in app
    assert "http://localhost:8000" not in app


# ------------------------------------------------------------------ CORS allow-list
def test_cors_defaults_are_exact_and_local():
    origins = allowed_origins(None, None)
    assert origins == list(DEFAULT_ORIGINS)
    assert "*" not in origins


def test_cors_adds_lan_origin_once():
    assert allowed_origins("", "192.168.1.42")[-1] == "https://192.168.1.42"
    o = allowed_origins("https://192.168.1.42", "192.168.1.42")
    assert o == ["https://192.168.1.42"]


def test_cors_custom_list_trims_and_dedupes():
    assert allowed_origins(" https://a.lan/ , https://a.lan,http://b:5173", None) == [
        "https://a.lan", "http://b:5173"]


@pytest.mark.parametrize("raw,lan", [("*", None), ("https://x,*", None), ("ftp://x", None),
                                     (None, "not-an-ip")])
def test_cors_rejects_wildcards_and_garbage(raw, lan):
    with pytest.raises(ValueError):
        allowed_origins(raw, lan)
