"""Base61 + XOR-checksum session id/token construction.

The observed app-layer pattern uses ``TS4``/``TR4`` prefixes, a base61-encoded
epoch timestamp, a random base36 tail and a XOR checksum seeded per field. The
prefix/seed/skip values are parameters so other endpoints can reuse the same
construction.
"""

from __future__ import annotations

import math
import random

_BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base61(value: int, width: int) -> str:
    out = [""] * width
    for index in range(width - 1, -1, -1):
        if value == 0 and index != width - 1:
            out[index] = "Z"
        else:
            digit = value % 61
            if digit < 10:
                out[index] = _BASE62[_BASE62.index("0") + digit]
            elif digit < 36:
                out[index] = _BASE62[_BASE62.index("a") + digit - 10]
            else:
                out[index] = _BASE62[_BASE62.index("A") + digit - 36]
        value = math.floor(value / 61)
    return "".join(out)


def _random_tail(rng: random.Random, width: int) -> str:
    return "".join(rng.choice(_BASE36) for _ in range(width))


def _checksum(text: str, seed: int, skip: tuple[int, ...] = ()) -> str:
    value = seed
    for index, char in enumerate(text):
        if index not in skip:
            value ^= ord(char)
    result = _base61(value, 2)
    return result if len(result) >= 2 else "Z" + result


def make_sid(epoch_seconds: int, rng: random.Random | None = None) -> str:
    """Build a ``TS4``-prefixed session id (skips checksum indexes 9 and 10)."""
    rng = rng if rng is not None else random.Random()
    time_part = _base61(epoch_seconds, 6)
    tail = _random_tail(rng, 8)
    seed = "TS4" + time_part + "ZZ" + tail
    return "TS4" + time_part + _checksum(seed, 57, skip=(9, 10)) + tail


def make_token(epoch_seconds: int, rng: random.Random | None = None) -> str:
    """Build a ``TR4``-prefixed session token (no skipped checksum indexes)."""
    rng = rng if rng is not None else random.Random()
    prefix = "TR4" + _base61(epoch_seconds, 6) + _random_tail(rng, 3)
    value = prefix + _random_tail(rng, 7)
    return value + _checksum(value, 122)
