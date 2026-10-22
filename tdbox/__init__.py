"""Tongdun ``black_box`` reverse-engineering study.

Pure-Python helpers reconstructed from the Tongdun 1.7.x device-fingerprint
SDK. No SDK source is bundled here; see ``scripts/extract_material.py`` to pull
the SDK out of your own mini-program plugin package.
"""

from .sign import encode_query, encode_query_value, header_sign
from .transform import token_id_to_black_box, validate_black_box

__all__ = [
    "token_id_to_black_box",
    "validate_black_box",
    "header_sign",
    "encode_query",
    "encode_query_value",
]

__version__ = "0.1.0"
