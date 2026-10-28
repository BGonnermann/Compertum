"""A checked model endpoint, based on the Vesper core endpoint."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Endpoint:
    scheme: str
    host: str
    ip: str
    port: int
    path: str

    def url(self, suffix: str = "") -> str:
        default = 443 if self.scheme == "https" else 80
        port = "" if self.port == default else f":{self.port}"
        return f"{self.scheme}://{self.host}{port}{self.path}{suffix}"


def parse(url: str) -> Endpoint:
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 or c == "\\" for c in url):
        raise ValueError("the model address is not valid")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("the model address is not valid")
    host = parts.hostname or ""
    if parts.scheme == "http" and host not in ("127.0.0.1", "localhost"):
        raise ValueError("a local model must use loopback")
    if parts.scheme == "https" and not host:
        raise ValueError("the model address is not valid")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = parts.path.rstrip("/")
    if path and (not path.startswith("/") or ".." in path.split("/")):
        raise ValueError("the model address is not valid")
    return Endpoint(parts.scheme, host, "127.0.0.1" if host == "localhost" else host, port, path)
