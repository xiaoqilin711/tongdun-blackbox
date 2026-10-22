"""Request-signing and query-encoding helpers (app-layer, site-agnostic)."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import quote

# encodeURIComponent leaves these characters unescaped.
_SAFE = "-_.!~*'()"


def header_sign(prefix: str, key: str, timestamp: str) -> str:
    """Compute the header ``sign`` as uppercase MD5(prefix + key + timestamp).

    The observed app uses ``prefix="wx-mini"`` and ``key="wx-minkey"``; both
    are parameters here so the same helper applies to other endpoints that
    reuse the "salt + timestamp" MD5 pattern.
    """
    return hashlib.md5((prefix + key + timestamp).encode("utf-8")).hexdigest().upper()


def encode_query_value(value) -> str:
    """Mirror JavaScript ``encodeURIComponent(JSON.stringify(value))``.

    Note the double encoding: the value is JSON-stringified first (so strings
    gain surrounding quotes), then URI-encoded (so ``"`` becomes ``%22``).
    """
    return quote(json.dumps(value, ensure_ascii=False), safe=_SAFE)


def encode_query(data: dict) -> dict:
    """Apply :func:`encode_query_value` to every field of ``data``."""
    return {key: encode_query_value(value) for key, value in data.items()}
