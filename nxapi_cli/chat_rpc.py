"""Publish a rich presence to the chat.boysare.moe RPC API.

This backend speaks HTTP instead of Discord's local IPC socket, so it works on
a headless server where no Discord client is running.
"""

import json

import requests

DEFAULT_RPC_URL = "https://chat.boysare.moe/api/rpc"
# Cloudflare rejects the default python-requests/urllib user agents.
USER_AGENT = "nxapi-cli/1.0 (+https://chat.boysare.moe)"
DEFAULT_TIMEOUT = 15
MAX_TEXT = 128


class ChatRPCError(Exception):
    """The chat.boysare.moe RPC endpoint refused or could not be reached."""


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text[:MAX_TEXT] or None


def _image(value):
    """The API only accepts http(s) URLs, not Discord asset keys."""
    url = _text(value)
    if url and url.startswith(("http://", "https://")):
        return url
    return None


def build_payload(kwargs, ttl):
    """Convert pypresence.update() kwargs into a chat.boysare.moe activity."""
    payload = {
        "type": "playing",
        "name": _text(kwargs.get("name")) or "Nintendo Switch",
        "expiresIn": int(ttl),
    }

    for key in ("details", "state"):
        value = _text(kwargs.get(key))
        if value:
            payload[key] = value

    assets = {
        "largeImage": _image(kwargs.get("large_image")),
        "largeText": _text(kwargs.get("large_text")),
        "smallImage": _image(kwargs.get("small_image")),
        "smallText": _text(kwargs.get("small_text")),
    }
    # Text without an image (or vice versa) is meaningless; drop empty pairs.
    if assets["largeImage"] or assets["smallImage"]:
        if not assets["largeImage"]:
            assets["largeText"] = None
        if not assets["smallImage"]:
            assets["smallText"] = None
        payload["assets"] = {k: v for k, v in assets.items() if v}

    start = kwargs.get("start")
    if start:
        try:
            payload["timestamps"] = {"start": int(start)}
        except (TypeError, ValueError):
            pass

    return payload


class ChatPresence:
    """Drop-in replacement for ``pypresence.Presence`` using the chat API."""

    def __init__(self, url=DEFAULT_RPC_URL, token="", ttl=90, session=None):
        self.url = str(url or DEFAULT_RPC_URL).rstrip("/")
        self.token = str(token or "")
        self.ttl = int(ttl)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            }
        )

    def _request(self, method, payload=None):
        try:
            response = self.session.request(
                method, self.url, json=payload, timeout=DEFAULT_TIMEOUT
            )
        except requests.RequestException as error:
            raise ChatRPCError(f"could not reach {self.url}: {error}") from error

        if response.ok:
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                return {}

        detail = response.text.strip()
        try:
            detail = json.loads(detail).get("error", detail)
        except (ValueError, AttributeError):
            pass
        raise ChatRPCError(f"HTTP {response.status_code}: {detail or 'request failed'}")

    def connect(self):
        if not self.token:
            raise ChatRPCError(
                "a chat.boysare.moe API token is required (set RPC_TOKEN "
                "or the rpc_token config option)"
            )
        # Read once so a bad/revoked token fails at startup rather than in the loop.
        self._request("GET")

    def update(self, **kwargs):
        return self._request("POST", build_payload(kwargs, self.ttl))

    def clear(self):
        return self._request("DELETE")

    def close(self):
        # Kept for parity with pypresence. The session is shared with the
        # presence poller, so leave it open for the next reconnect.
        pass
