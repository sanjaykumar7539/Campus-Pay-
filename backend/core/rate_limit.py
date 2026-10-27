from __future__ import annotations

import os
import threading
import time
import hashlib
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from core.errors import error_body

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

def _rule(path: str) -> tuple[str, int, int]:
    if path.endswith(("/auth/login", "/auth/student-login", "/kiosk/logout", "/kiosk/setup")):
        return ("auth", 10, 60)
    if path.endswith("/pay"):
        return ("payment", 20, 60)
    if path.startswith("/api/v1/printer/") or path.startswith("/api/v1/scanner/") or path.startswith("/api/v1/kiosk/"):
        return ("station", 180, 60)
    return ("api", 120, 60)

async def rate_limit_middleware(request: Request, call_next):
    # Automated tests share one synthetic client IP; production/local/demo limits remain enabled.
    if os.getenv("ENVIRONMENT", "local").strip().lower() == "test":
        return await call_next(request)
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    bucket, limit, window = _rule(request.url.path)
    host = request.client.host if request.client else "unknown"
    # Auth attempts stay IP-scoped. Station polling is separated by its credential
    # so multiple kiosks behind one campus NAT do not consume the same bucket.
    identity = ""
    if bucket == "station":
        identity = request.headers.get("X-Printer-Token") or request.headers.get("X-Scanner-Token") or request.cookies.get("cp_kiosk", "")
    key = (host + (":" + hashlib.sha256(identity.encode()).hexdigest()[:24] if identity else ""), bucket)
    now = time.monotonic()
    with _lock:
        if len(_hits) > 10000:
            for stale in [k for k, v in _hits.items() if not v or v[-1] <= now - 60]:
                _hits.pop(stale, None)
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        remaining = max(0, limit - len(q))
        if len(q) >= limit:
            retry = max(1, int(window - (now - q[0])))
            return JSONResponse(status_code=429, content=error_body("RATE_LIMITED", "Too many requests. Try again shortly."),
                                headers={"Retry-After": str(retry), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"})
        q.append(now)
        remaining = max(0, limit - len(q))
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
