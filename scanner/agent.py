"""Hardware-neutral native scanner worker. No simulated matching implementation.

Run on a protected scanner host, never inside a browser. See INTEGRATION.md.
"""
import importlib
import json
import logging
import os
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError

log = logging.getLogger("campuspay.scanner")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Scanner API redirects are forbidden")


def main():
    logging.basicConfig(level=logging.INFO)
    server = os.environ["CAMPUSPAY_SERVER"].rstrip("/")
    token = os.environ["CAMPUSPAY_SCANNER_TOKEN"]
    module = os.environ["CAMPUSPAY_SCANNER_ADAPTER"]
    parsed = urlparse(server)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
        and os.getenv("CAMPUSPAY_SCANNER_LOCAL_TEST") == "true"
    ):
        raise RuntimeError("Scanner communication requires HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("Use a plain HTTPS origin as CAMPUSPAY_SERVER")
    adapter = importlib.import_module(module).Scanner()
    # Must fail startup if hardware, matcher or SDK is unavailable.
    adapter.open()
    opener = build_opener(NoRedirect())

    def api(path, body=None):
        request = Request(server + "/api/v1" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "X-Scanner-Token": token},
            method="POST" if body is not None else "GET")
        with opener.open(request, timeout=15) as response:
            return json.load(response)["data"]

    try:
        while True:
            try:
                for job in api("/scanner/jobs"):
                    # Adapter MUST wait for removal after every capture, including
                    # retries and restarts. capture_id is persisted and globally unique
                    # per acquisition, never regenerated to retry the same capture.
                    result = adapter.capture(job, timeout_seconds=15)
                    if result is None:
                        continue
                    payload = {"nonce": job["nonce"], "capture_id": result["capture_id"],
                        "matched": result["matched"], "finger_ref": result.get("finger_ref")}
                    api("/scanner/jobs/" + job["id"] + "/capture", payload)
                    adapter.release(job)
            except HTTPError as exc:
                if exc.code in (401, 403):
                    raise RuntimeError("Scanner authorization rejected; contact the administrator") from exc
                log.warning("Server refused scanner operation (HTTP %s); waiting for the next job", exc.code)
            except (URLError, TimeoutError):
                log.warning("Scanner service cannot reach the server; no offline payments permitted")
            time.sleep(2)
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
