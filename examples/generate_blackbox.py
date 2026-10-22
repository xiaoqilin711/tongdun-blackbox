#!/usr/bin/env python3
"""Generate a fresh Tongdun ``black_box`` with SpiderMonkey and Firefox Necko.

Pipeline::

    SpiderMonkey (browser-env)  ->  FMAgent.getInfo()  ->  capture profile.json
    Firefox Necko               ->  POST fp.tongdun.net/wxapp/profile.json
                                 ->  code=000, tokenId (23 chars)
    tdbox.transform             ->  tokenId -> black_box (26 chars)

Requires the xiaojianbang runtime set (browser-env + Firefox JS + Necko) and a
Tongdun 1.7.x SDK extracted with ``scripts/extract_material.py``. Neither the
runtime nor the SDK is redistributed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# The repository root (examples/../).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make tdbox importable when run as a script

# Default xiaojianbang runtime roots. Override with the XJB_* environment vars
# if your install lives elsewhere.
RELEASES = Path(r"C:\mozilla-build-outputs\releases")
DEFAULT_ENV = RELEASES / "xiaojianbang-browser-env-1.4.0" / "xiaojianbang-browser-env"
DEFAULT_JS = RELEASES / "xiaojianbang-js-runtime-min-windows-x86_64-20260827"
DEFAULT_NECKO = RELEASES / "xiaojianbang-necko-runtime-min-windows-x86_64-20260827"

SDK = ROOT / "material" / "tdfp_fm_1.7.7.js"
PROFILE_DRIVER = ROOT / "js" / "profile_driver.js"
TOKEN_DRIVER = ROOT / "js" / "token_driver.js"
PROFILE = ROOT / "examples" / "profile.example.json"

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


def unload_firefox_runtime() -> None:
    for module_name in list(sys.modules):
        if module_name == "firefox_py_runtime" or module_name.startswith("firefox_py_runtime."):
            del sys.modules[module_name]


def run_spidermonkey(driver: Path, material: dict[str, Any], env_root: Path, js_root: Path, sdk: Path) -> dict[str, Any]:
    unload_firefox_runtime()
    sys.path[:] = [entry for entry in sys.path if "xiaojianbang-necko-runtime-min-" not in str(entry)]
    sys.path.insert(0, str(env_root))
    from tools.spidermonkey_runner import SpiderMonkeyRunner  # type: ignore

    runner = SpiderMonkeyRunner(runtime_root=js_root)
    result = runner.run(
        [env_root / "src" / "core.js", env_root / "src" / "adapters" / "spidermonkey.js", sdk, driver],
        script_args=[json.dumps(material, ensure_ascii=False, separators=(",", ":"))],
        cwd=ROOT,
        timeout=60,
    )
    return result.payload


def runtime_manifest(profile: dict[str, Any], sdk: Path) -> dict[str, Any]:
    return {
        "engine": "xiaojianbang Firefox SpiderMonkey",
        "runtimeVersion": "152.0.3",
        "profileId": profile["meta"]["id"],
        "profileHash": file_sha256(PROFILE),
        "scriptHashes": {
            sdk.name: file_sha256(sdk),
            PROFILE_DRIVER.name: file_sha256(PROFILE_DRIVER),
            TOKEN_DRIVER.name: file_sha256(TOKEN_DRIVER),
        },
    }


def generate(args: argparse.Namespace) -> dict[str, Any]:
    sdk = Path(args.sdk or SDK).resolve()
    env_root = Path(os.environ.get("XJB_BROWSER_ENV", DEFAULT_ENV)).resolve()
    js_root = Path(os.environ.get("XJB_FIREFOX_JS_RUNTIME", DEFAULT_JS)).resolve()
    necko_root = Path(os.environ.get("XJB_NECKO_RUNTIME", DEFAULT_NECKO)).resolve()
    for required in (env_root, js_root, necko_root, sdk, PROFILE_DRIVER, TOKEN_DRIVER, PROFILE):
        if not required.exists():
            raise FileNotFoundError(required)

    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    host_file = Path(args.host_inputs or ROOT / "examples" / "host-inputs.example.json").resolve()
    host_inputs = json.loads(host_file.read_text(encoding="utf-8"))
    if host_inputs.get("schema") != "host-inputs-v1":
        raise ValueError("invalid host-inputs schema")
    manifest = runtime_manifest(profile, sdk)

    profile_result = run_spidermonkey(
        PROFILE_DRIVER,
        {
            "profile": profile,
            "hostInputs": host_inputs,
            "manifest": manifest,
            "partnerCode": args.partner,
            "appName": args.app_name,
            "openid": args.openid,
            "unionid": args.unionid,
        },
        env_root,
        js_root,
        sdk,
    )
    if profile_result.get("status") != "profile-ready":
        raise RuntimeError(f"profile generation failed: {profile_result}")

    request = profile_result["request"]
    if request.get("method", "").upper() != "POST" or request["url"] != (
        "https://fp.tongdun.net/wxapp/profile.json?" + urlencode({"partner": args.partner})
    ):
        raise ValueError("unexpected SDK request method/endpoint")
    form = urlencode(request["data"]).encode("utf-8")

    events: list[dict[str, Any]] = []
    unload_firefox_runtime()
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != js_root]
    sys.path.insert(0, str(necko_root))
    from firefox_py_runtime.net import FirefoxNeckoSession  # type: ignore

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": USER_AGENT,
        "Referer": "https://servicewechat.com/wxac2907********/212/page-frame.html",
    }
    with FirefoxNeckoSession(event_sink=events, high_trust=True) as session:
        response = session.post(request["url"], data=form, headers=headers, timeout=args.timeout)
    necko_snapshot = session.snapshot()
    necko_parity = session.export_parity()

    try:
        payload = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Tongdun response is not UTF-8 JSON: HTTP {response.status_code}") from error
    result = payload.get("result") or {}
    token_id = str(result.get("tokenId") or "")
    if response.status_code != 200 or payload.get("code") != "000" or len(token_id) != 23:
        raise RuntimeError(f"Tongdun profile rejected: HTTP {response.status_code}, payload={payload}")

    # Local transform: pure-Python tdbox implementation. The SDK's own Z()
    # (js/token_driver.js) is run only when --cross-check is set, because its
    # inserted chars are random and differ from the Python RNG's — so the two
    # are compared structurally (validate_black_box), not byte-for-byte.
    from tdbox.transform import token_id_to_black_box, validate_black_box

    black_box = token_id_to_black_box(token_id)
    if not validate_black_box(token_id, black_box):
        raise RuntimeError("token transformation structural verification failed")

    cross_check: dict[str, Any] | None = None
    if args.cross_check:
        cross_result = run_spidermonkey(
            TOKEN_DRIVER,
            {"profile": profile, "manifest": manifest, "tokenId": token_id},
            env_root,
            js_root,
            sdk,
        )
        if cross_result.get("status") != "blackbox-ready":
            raise RuntimeError(f"token cross-check failed: {cross_result}")
        sdk_black_box = cross_result["blackBox"]
        cross_check = {
            "sdkBlackBox": sdk_black_box,
            "structurallyConsistent": validate_black_box(token_id, sdk_black_box),
        }

    generated_at = datetime.now(timezone.utc).isoformat()
    output = {
        "schema": "blackbox-v1",
        "ok": True,
        "generatedAt": generated_at,
        "black_box": black_box,
        "blackBoxLength": len(black_box),
        "tokenId": token_id,
        "tokenIdLength": len(token_id),
        "localTransformVerified": True,
        "crossCheck": cross_check,
        "xxid": result.get("xxid"),
        "factor": (result.get("c") or {}).get("factor"),
        "validitySeconds": (result.get("c") or {}).get("vt"),
        "profile": {
            "url": request["url"],
            "formBytes": len(form),
            "formSha256": hashlib.sha256(form).hexdigest(),
            "fieldNames": list(request["data"]),
        },
        "runtime": {
            "js": "xiaojianbang Firefox SpiderMonkey 152.0.3",
            "network": "Firefox Necko",
            "browserEnv": "xiaojianbang-browser-env-1.4.0",
            "neckoAuditState": necko_snapshot.get("audit_state"),
        },
        "response": {
            "httpStatus": response.status_code,
            "code": payload.get("code"),
            "desc": payload.get("desc"),
            "bodyBytes": len(response.content),
            "bodySha256": hashlib.sha256(response.content).hexdigest(),
        },
    }
    if args.json_out:
        path = args.json_out.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        event_path = path.with_name(path.stem + ".necko.jsonl")
        event_path.write_text("".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")
        parity_path = path.with_name(path.stem + ".parity.json")
        parity_path.write_text(json.dumps(necko_parity, ensure_ascii=False, indent=2), encoding="utf-8")
        output["artifacts"] = {"result": str(path), "neckoEvents": str(event_path), "neckoParity": str(parity_path)}
    return output


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Generate a fresh Tongdun black_box without WMPF/WebView")
    value.add_argument("--partner", default="9air")
    value.add_argument("--app-name", default="9air_xcx")
    value.add_argument("--openid", default="anonymous")
    value.add_argument("--unionid", default="")
    value.add_argument("--timeout", type=float, default=30)
    value.add_argument("--json-out", type=Path)
    value.add_argument("--sdk", type=Path, help="explicit extracted SDK file (default: material/tdfp_fm_1.7.7.js)")
    value.add_argument("--host-inputs", type=Path, help="explicit host inputs (default: examples/host-inputs.example.json)")
    value.add_argument("--cross-check", action="store_true", help="also run the SDK's own Z() and verify structural consistency")
    value.add_argument("--redact", action="store_true", help="hide fresh token/black_box in stdout; json-out retains them")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        result = generate(args)
        if args.redact:
            result = dict(result)
            for key in ("black_box", "tokenId", "xxid", "factor"):
                value = result.pop(key, None)
                if value is not None:
                    result[key + "Sha256"] = hashlib.sha256(str(value).encode()).hexdigest()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
