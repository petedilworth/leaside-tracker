"""One place that talks to the network, so throttling, identity and retries stay consistent."""
from __future__ import annotations

import time

import requests

_last_call: dict[str, float] = {}

RETRYABLE = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)


class Fetcher:
    def __init__(self, user_agent: str, timeout: int = 30, delay: float = 2.0, retries: int = 2):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                # Some municipal sites sit behind a firewall that rejects requests with
                # no Accept header at all. Sending honest ones is not impersonation.
                "Accept": "application/json, application/rss+xml, application/xml;q=0.9,"
                " text/html;q=0.8, */*;q=0.5",
                "Accept-Language": "en-CA,en;q=0.9",
            }
        )
        self.timeout = timeout
        self.delay = delay
        self.retries = retries

    def get(self, url: str, timeout: int | None = None, retries: int | None = None, **kwargs):
        timeout = timeout or self.timeout
        attempts = (retries if retries is not None else self.retries) + 1
        host = url.split("/")[2] if "//" in url else url
        last_error = None
        for attempt in range(attempts):
            wait = self.delay - (time.monotonic() - _last_call.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=timeout, **kwargs)
                _last_call[host] = time.monotonic()
                return resp
            except RETRYABLE as exc:
                _last_call[host] = time.monotonic()
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(2 ** attempt)  # 1s, then 2s, then 4s
        raise last_error
