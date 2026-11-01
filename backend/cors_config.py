"""Allowed CORS origins (Task 1).

In the Docker setup the browser talks to Nginx on the same origin (https://<host>/api/...), so CORS
is not exercised at all. This list only matters if someone points a frontend at the backend
directly; it replaces the previous allow_origins=["*"] with an exact allow-list.
"""

from __future__ import annotations

import ipaddress
from typing import List, Optional

DEFAULT_ORIGINS = (
    "https://localhost",
    "https://127.0.0.1",
    # Vite dev server (npm run dev), bare-metal development only.
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def allowed_origins(raw: Optional[str], lan_ip: Optional[str]) -> List[str]:
    """Build the allow-list from CORS_ALLOW_ORIGINS (comma separated) and SERVER_LAN_IP.

    - Empty/unset CORS_ALLOW_ORIGINS -> DEFAULT_ORIGINS.
    - SERVER_LAN_IP, when it is a valid IP, adds https://<ip>.
    - "*" is rejected: a wildcard is exactly what this replaces.
    """
    if raw and raw.strip():
        origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    else:
        origins = list(DEFAULT_ORIGINS)

    if "*" in origins:
        raise ValueError("CORS_ALLOW_ORIGINS must list exact origins; '*' is not allowed")
    for o in origins:
        if not (o.startswith("https://") or o.startswith("http://")):
            raise ValueError(f"CORS origin must start with http:// or https://: {o!r}")

    if lan_ip and lan_ip.strip():
        ip = ipaddress.ip_address(lan_ip.strip())  # raises ValueError on garbage
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        lan_origin = f"https://{host}"
        if lan_origin not in origins:
            origins.append(lan_origin)

    # keep order, drop duplicates
    seen, out = set(), []
    for o in origins:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out
