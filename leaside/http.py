"""One place that talks to the network, so throttling and identification are consistent."""
from __future__ import annotations

import time

import requests

_last_call: dict[str, float] = {}


class Fetcher:
    def __init__(self, user_agent: str, timeout: int = 30, delay: float = 2.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.timeout = timeout
        self.delay = delay

    def get(self, url: str, **kwargs) -> requests.Response:
        host = url.split("/")[2] if "//" in url else url
        wait = self.delay - (time.monotonic() - _last_call.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        _last_call[host] = time.monotonic()
        return resp
