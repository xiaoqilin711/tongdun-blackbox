#!/usr/bin/env python3
"""Extract the Tongdun 1.7.x SDK from a mini-program plugin source file.

The SDK source is NOT redistributed in this repository. Run this script against
your own WMPF trace's ``scripts/source/*.js`` sidecar to pull out the SDK line
and wrap it with the minimal module shim the SpiderMonkey drivers expect.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

WRAPPER = """'use strict';
var exports = {};
var module = { exports: exports };
function require(name) {
  if (name !== '../@babel/runtime/helpers/typeof') throw new Error('unexpected require: ' + name);
  return function _typeof(value) {
    return typeof Symbol === 'function' && typeof Symbol.iterator === 'symbol'
      ? typeof value
      : value && typeof Symbol === 'function' && value.constructor === Symbol && value !== Symbol.prototype
        ? 'symbol'
        : typeof value;
  };
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="plugin source .js file from the WMPF trace")
    parser.add_argument("--line", type=int, required=True,
                        help="1-based line index of the SDK module line")
    parser.add_argument("--prefix", default='"use strict";Object.defineProperty(exports,"__esModule"',
                        help="expected line prefix")
    parser.add_argument("--suffix", default="exports.default=Tn; ",
                        help="expected line suffix")
    parser.add_argument("--output", type=Path, default=Path("material/tdfp_fm_1.7.7.js"))
    args = parser.parse_args()

    lines = args.source.read_text(encoding="utf-8").splitlines()
    index = args.line - 1
    if index < 0 or index >= len(lines):
        raise SystemExit(f"line {args.line} out of range (file has {len(lines)} lines)")

    sdk = lines[index]
    if not sdk.startswith(args.prefix) or not sdk.endswith(args.suffix):
        raise SystemExit("target line does not match the expected prefix/suffix")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(WRAPPER + sdk + "\nvar FMAgent = exports.default;\n",
                           encoding="utf-8", newline="\n")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f"extracted={args.output}")
    print(f"bytes={args.output.stat().st_size}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
