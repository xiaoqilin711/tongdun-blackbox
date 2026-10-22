"""Tongdun 1.7.x ``black_box`` local transform (``tokenId`` -> ``black_box``).

Re-implements the SDK's ``Z()`` transform as pure Python, so a fresh 23-char
``tokenId`` issued by ``fp.tongdun.net/wxapp/profile.json`` can be turned into
the 26-char ``black_box`` consumed by the business API without running the SDK.

Reference (from the de-obfuscated 1.7.7 SDK)::

    function L(n) {
        var t = n.charAt(0);
        var r = "ghijklmnopqrstuv".charAt("0123456789abcdef".indexOf(t));
        return F(F(F(n.replace(t, r), 4), 15), 24);
    }

where ``F(s, i)`` inserts one random base62 char at index ``i``.
"""

from __future__ import annotations

import random
import string

# The tokenId must start AND end with one of these; the SDK leaves the token
# unchanged (no transform) otherwise.
TOKEN_ALPHABET = "0123456789abcdef"
# First-char mapping target, one entry per TOKEN_ALPHABET char.
PREFIX_ALPHABET = "ghijklmnopqrstuv"
# Random chars inserted at these slots; ascending order keeps indexes valid.
INSERT_INDEXES = (4, 15, 24)
INSERT_ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits

TOKEN_LENGTH = 23
BLACKBOX_LENGTH = 26


def _map_first_char(char: str) -> str:
    return PREFIX_ALPHABET[TOKEN_ALPHABET.index(char)]


def _restore_first_char(char: str) -> str:
    return TOKEN_ALPHABET[PREFIX_ALPHABET.index(char)]


def token_id_to_black_box(token_id: str, rng: random.Random | None = None) -> str:
    """Transform a 23-char ``tokenId`` into a 26-char ``black_box``.

    Args:
        token_id: the 23-char token issued by the Tongdun profile endpoint.
        rng: optional seeded :class:`random.Random` for deterministic output.

    Returns:
        A 26-char ``black_box`` string.

    Raises:
        ValueError: if the token does not have the expected shape. The SDK
            leaves a token unchanged when its first or last char is not hex;
            we raise instead so callers never silently get an untransformed
            value.
    """
    if rng is None:
        rng = random.Random()
    if len(token_id) != TOKEN_LENGTH:
        raise ValueError(f"tokenId must be {TOKEN_LENGTH} chars, got {len(token_id)}")
    if token_id[0] not in TOKEN_ALPHABET or token_id[-1] not in TOKEN_ALPHABET:
        raise ValueError("tokenId must start and end with a hex char (0-9a-f)")

    chars = [_map_first_char(token_id[0])] + list(token_id[1:])
    for index in INSERT_INDEXES:
        chars.insert(index, rng.choice(INSERT_ALPHABET))
    return "".join(chars)


def validate_black_box(token_id: str, black_box: str) -> bool:
    """Reverse :func:`token_id_to_black_box` and check structural equality.

    Strip the three inserted chars (indexes 24, 15, 4 in that order) and unmap
    the first char; the result must equal the original ``token_id``.
    """
    if len(token_id) != TOKEN_LENGTH or len(black_box) != BLACKBOX_LENGTH:
        return False
    restored = list(black_box)
    for index in reversed(INSERT_INDEXES):
        restored.pop(index)
    if restored[0] not in PREFIX_ALPHABET:
        return False
    restored[0] = _restore_first_char(restored[0])
    return "".join(restored) == token_id
