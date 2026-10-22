#!/usr/bin/env python3
"""Pure-protocol flight-search client for the 9 Air mini-program (case study).

Evidence comes from a WMPF trace of ``/thirdpart/res/wx/mina/searchFlight`` and
the ``app-service/tdfp-plugin`` source. SpiderMonkey runs the original
``FMAgent.sign`` inside a browser-env production host; Python orchestrates the
same-session flow and submits UTF-8 JSON via Firefox Necko.

This is a redacted case study: the real app id and any live session material
are NOT committed. Supply ``--openid`` / ``--black-box`` (or let a black_box be
generated) to reproduce the request against your own account.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make tdbox importable when run as a script

RELEASES = Path(r"C:\mozilla-build-outputs\releases")
DEFAULT_ENV = RELEASES / "xiaojianbang-browser-env-1.4.0" / "xiaojianbang-browser-env"
DEFAULT_JS = RELEASES / "xiaojianbang-js-runtime-min-windows-x86_64-20260827"
DEFAULT_NECKO = RELEASES / "xiaojianbang-necko-runtime-min-windows-x86_64-20260827"

SEARCH_PATH = "/thirdpart/res/wx/mina/searchFlight"
SEARCH_URL = "https://api.9air.com" + SEARCH_PATH

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf2541d0c) XWEB/25510"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def trace_session_material(trace_root: Path) -> tuple[str, str]:
    """Extract a short-lived openid/black_box from a prior searchFlight trace.

    This is intentionally an explicit, opt-in path (``--reuse-trace-black-box``)
    so no live material is baked into the repository.
    """
    path = trace_root / "normalized" / "http.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"trace HTTP log not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
            request = event.get("data", {}).get("request", {})
            if "searchFlight" not in request.get("url", ""):
                continue
            body = json.loads(request.get("postData") or "{}")
            anti = json.loads(body.get("Anti-Headers") or "{}")
            openid = str(anti.get("openid") or "")
            black_box = str(anti.get("black_box") or "")
            if openid and black_box:
                return openid, black_box
        except (json.JSONDecodeError, TypeError):
            continue
    raise RuntimeError("trace has no complete session material; pass --openid and --black-box explicitly")


def generate_headers_and_anti(body: dict[str, Any], env_root: Path, js_root: Path) -> dict[str, Any]:
    """Run the original FMAgent.sign in SpiderMonkey to produce the inner sign."""
    sys.path.insert(0, str(env_root))
    from tools.spidermonkey_runner import SpiderMonkeyRunner  # type: ignore

    profile_path = ROOT / "examples" / "profile.example.json"
    sdk_path = ROOT / "material" / "tdfp_fm_1.7.7.js"
    driver_path = ROOT / "js" / "sign_driver.js"
    if not sdk_path.is_file():
        raise FileNotFoundError(f"extracted Tongdun SDK missing: {sdk_path}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    manifest = {
        "engine": "xiaojianbang Firefox SpiderMonkey",
        "runtimeVersion": "152.0.3",
        "profileId": profile["meta"]["id"],
        "profileHash": file_sha256(profile_path),
        "scriptHashes": {
            "tdfp_fm_1.7.7.js": file_sha256(sdk_path),
            "sign_driver.js": file_sha256(driver_path),
        },
    }
    material = json.dumps(
        {"profile": profile, "manifest": manifest, "path": SEARCH_PATH, "body": body,
         "prefix": "wx-mini", "key": "wx-minkey"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    runner = SpiderMonkeyRunner(runtime_root=js_root)
    result = runner.run(
        [env_root / "src" / "core.js", env_root / "src" / "adapters" / "spidermonkey.js", sdk_path, driver_path],
        script_args=[material],
        cwd=ROOT,
        timeout=60,
    )
    if result.payload.get("status") != "passed":
        raise RuntimeError(f"SpiderMonkey sign failed: {result.payload}")
    manifest_result = result.payload.get("manifest") or {}
    if not manifest_result.get("productionReady"):
        raise RuntimeError(f"browser-env production check failed: {manifest_result}")
    if len(result.payload.get("antiSign", "")) != 168:
        raise RuntimeError("FMAgent.sign output length is not 168")
    return result.payload


def summarize_flights(payload: dict[str, Any]) -> list[dict[str, Any]]:
    flights = ((payload.get("data") or {}).get("flights") or [])
    summary: list[dict[str, Any]] = []
    for flight in flights:
        segment = flight.get("segments") or {}
        fares = flight.get("fares") or []
        prices = [fare.get("price") for fare in fares if isinstance(fare.get("price"), (int, float))]
        summary.append(
            {
                "flightId": flight.get("flightId"),
                "flightNo": f"{segment.get('marketAirlineCode') or ''}{segment.get('marketFlightNo') or ''}",
                "departure": segment.get("departAirportCode"),
                "arrival": segment.get("arrivalAirportCode"),
                "departDate": segment.get("departDate"),
                "departTime": segment.get("departTime"),
                "arrivalDate": segment.get("arrivalDate"),
                "arrivalTime": segment.get("arrivalTime"),
                "lowestPrice": segment.get("lowestPrice") if segment.get("lowestPrice") is not None else (min(prices) if prices else None),
                "currency": fares[0].get("currency") if fares else None,
            }
        )
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    env_root = Path(os.environ.get("XJB_BROWSER_ENV", DEFAULT_ENV)).resolve()
    js_root = Path(os.environ.get("XJB_FIREFOX_JS_RUNTIME", DEFAULT_JS)).resolve()
    necko_root = Path(os.environ.get("XJB_NECKO_RUNTIME", DEFAULT_NECKO)).resolve()
    for required in (env_root, js_root, necko_root):
        if not required.is_dir():
            raise FileNotFoundError(required)

    openid = args.openid if args.openid is not None else os.environ.get("XJB_9AIR_OPENID", "anonymous")
    black_box = args.black_box if args.black_box is not None else os.environ.get("XJB_9AIR_BLACK_BOX")
    black_box_source = "argument" if args.black_box is not None else "environment" if black_box is not None else "generated"
    black_box_generation: dict[str, Any] | None = None
    if black_box is None and getattr(args, "reuse_trace_black_box", False):
        if not args.trace_root:
            raise ValueError("--reuse-trace-black-box requires --trace-root")
        _, black_box = trace_session_material(args.trace_root)
        black_box_source = "trace"
    elif black_box is None:
        from generate_blackbox import generate as generate_black_box

        generator_output = args.json_out.with_name(args.json_out.stem + ".blackbox.json") if args.json_out else None
        black_box_generation = generate_black_box(argparse.Namespace(
            partner="9air",
            app_name="9air_xcx",
            openid=openid,
            unionid="",
            timeout=args.timeout,
            json_out=generator_output,
            sdk=None,
            host_inputs=None,
            cross_check=False,
        ))
        black_box = str(black_box_generation["black_box"])
    if not openid or not black_box:
        raise ValueError("openid and black_box are required; pass current session material")

    arrival_date = args.arrival_date or (args.depart_date + timedelta(days=1))
    body: dict[str, Any] = {
        "depType": args.departure_type,
        "arrType": args.arrival_type,
        "tripType": args.trip_type,
        "departDate": args.depart_date.isoformat(),
        "arrivalDate": arrival_date.isoformat(),
        "departure": args.departure.upper(),
        "arrival": args.arrival.upper(),
        "promotionID": args.promotion_id,
        "channelNo": "XCX",
        "currency": args.currency,
    }
    generated = generate_headers_and_anti(body, env_root, js_root)

    # Session id / token: pure-Python reconstruction (see tdbox/session.py).
    from tdbox.session import make_sid, make_token

    epoch_seconds = int(time.time())
    sid = make_sid(epoch_seconds)
    sw_token = make_token(epoch_seconds)

    anti_headers = {
        "black_box": black_box,
        "channel": "9air_xcx",
        "token": "",
        "openid": openid,
        "path": SEARCH_PATH,
        "query": json.dumps(generated["query"], ensure_ascii=False, separators=(",", ":")),
        "sign": generated["antiSign"],
    }
    request_body = dict(body)
    request_body["Anti-Headers"] = json.dumps(anti_headers, ensure_ascii=False, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "Accept-Language": "zh",
        "User-Agent": USER_AGENT,
        "Referer": "https://servicewechat.com/wxac2907********/212/page-frame.html",
        "appId": "wx-mini",
        "timestamp": generated["timestamp"],
        "sign": generated["appSign"],
        "memberId": "",
        "token": "",
        "environment": "webDiscounts",
        "x-s3-sid": sid,
        "x-sw-token": sw_token,
        "x-sw-sk": "",
        "Anti-Headers": "",
    }

    for module_name in list(sys.modules):
        if module_name == "firefox_py_runtime" or module_name.startswith("firefox_py_runtime."):
            del sys.modules[module_name]
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != js_root]
    sys.path.insert(0, str(necko_root))
    from firefox_py_runtime.net import FirefoxNeckoSession  # type: ignore

    events: list[dict[str, Any]] = []
    started = datetime.now().astimezone().isoformat()
    with FirefoxNeckoSession(event_sink=events, high_trust=True) as session:
        response = session.post(SEARCH_URL, json=request_body, headers=headers, timeout=args.timeout)
    snapshot = session.snapshot()
    parity = session.export_parity()
    try:
        response_payload = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"response is not UTF-8 JSON: status={response.status_code}, bytes={len(response.content)}") from error
    business_ok = response.status_code == 200 and response_payload.get("msg") == "message.result.ok"
    result = {
        "ok": business_ok,
        "startedAt": started,
        "request": {
            "method": "POST",
            "url": SEARCH_URL,
            "route": {
                "departure": request_body["departure"],
                "arrival": request_body["arrival"],
                "departDate": request_body["departDate"],
                "arrivalDate": request_body["arrivalDate"],
                "tripType": request_body["tripType"],
            },
            "bodyBytes": len(json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
            "antiSignLength": len(generated["antiSign"]),
            "blackBoxLength": len(black_box),
            "blackBoxSha256": hashlib.sha256(black_box.encode("utf-8")).hexdigest(),
            "blackBoxSource": black_box_source,
        },
        "runtime": {
            "js": "xiaojianbang Firefox SpiderMonkey 152.0.3",
            "network": "Firefox Necko",
            "browserEnv": "xiaojianbang-browser-env-1.4.0",
            "manifest": generated["manifest"],
            "neckoAuditState": snapshot.get("audit_state"),
        },
        "response": {
            "httpStatus": response.status_code,
            "classification": response.classification,
            "bodyBytes": len(response.content),
            "bodySha256": hashlib.sha256(response.content).hexdigest(),
            "status": response_payload.get("status"),
            "code": response_payload.get("code"),
            "msg": response_payload.get("msg"),
            "message": response_payload.get("message"),
            "sessionId": (response_payload.get("data") or {}).get("sessionId"),
            "flightCount": len((response_payload.get("data") or {}).get("flights") or []),
            "flights": summarize_flights(response_payload),
        },
    }
    if black_box_generation:
        result["blackBoxGeneration"] = {
            "generatedAt": black_box_generation["generatedAt"],
            "tokenIdLength": black_box_generation["tokenIdLength"],
            "localTransformVerified": black_box_generation["localTransformVerified"],
            "profile": black_box_generation["profile"],
            "response": black_box_generation["response"],
            "artifacts": black_box_generation.get("artifacts"),
        }
    if args.json_out:
        output = args.json_out.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"summary": result, "data": response_payload, "neckoParity": parity}, ensure_ascii=False, indent=2), encoding="utf-8")
        events_path = output.with_name(output.stem + ".necko.jsonl")
        events_path.write_text("".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")
        result["output"] = {"response": str(output), "neckoEvents": str(events_path)}
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="9 Air mini-program flight-search pure-protocol client (redacted case study)")
    parser.add_argument("--departure", required=True, help="departure city/airport code, e.g. CAN")
    parser.add_argument("--arrival", required=True, help="arrival city/airport code, e.g. BJS")
    parser.add_argument("--depart-date", required=True, type=parse_date, help="departure date YYYY-MM-DD")
    parser.add_argument("--arrival-date", type=parse_date, help="return date; defaults to depart-date + 1 day")
    parser.add_argument("--trip-type", choices=("OW", "RT"), default="OW")
    parser.add_argument("--departure-type", choices=("CITY", "AIRPORT"), default="CITY")
    parser.add_argument("--arrival-type", choices=("CITY", "AIRPORT"), default="CITY")
    parser.add_argument("--promotion-id", default="")
    parser.add_argument("--currency", default="CNY")
    parser.add_argument("--reuse-trace-black-box", action="store_true", help="reuse a black_box from a prior trace (requires --trace-root)")
    parser.add_argument("--trace-root", type=Path, help="trace run directory for extracting session material")
    parser.add_argument("--openid", default=None, help="request context; or XJB_9AIR_OPENID, default 'anonymous'")
    parser.add_argument("--black-box", default=None, help="explicit black_box; or XJB_9AIR_BLACK_BOX; generated when absent")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--json-out", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
