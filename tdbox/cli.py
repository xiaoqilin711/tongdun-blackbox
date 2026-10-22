"""Command-line interface for the ``tdbox`` helpers."""

from __future__ import annotations

import argparse
import json
import random
import sys

from .sign import encode_query, header_sign
from .session import make_sid, make_token
from .transform import token_id_to_black_box, validate_black_box


def _cmd_transform(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed) if args.seed is not None else None
    try:
        print(token_id_to_black_box(args.token_id, rng))
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    ok = validate_black_box(args.token_id, args.black_box)
    print(json.dumps({"valid": ok}))
    return 0 if ok else 1


def _cmd_sign(args: argparse.Namespace) -> int:
    print(header_sign(args.prefix, args.key, args.timestamp))
    return 0


def _cmd_encode(args: argparse.Namespace) -> int:
    data = json.loads(args.json)
    print(json.dumps(encode_query(data), ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tdbox",
        description="Tongdun black_box transform and request-signing helpers",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("transform", help="transform a 23-char tokenId into a 26-char black_box")
    p.add_argument("token_id")
    p.add_argument("--seed", type=int, default=None, help="deterministic RNG seed (for tests)")
    p.set_defaults(func=_cmd_transform)

    p = sub.add_parser("validate", help="verify a black_box against its tokenId")
    p.add_argument("token_id")
    p.add_argument("black_box")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("sign", help="header sign = MD5(prefix + key + timestamp)")
    p.add_argument("prefix")
    p.add_argument("key")
    p.add_argument("timestamp")
    p.set_defaults(func=_cmd_sign)

    p = sub.add_parser("encode", help="encodeURIComponent(JSON.stringify()) each field")
    p.add_argument("json", help="JSON object whose fields should be encoded")
    p.set_defaults(func=_cmd_encode)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
