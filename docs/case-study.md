# From a WMPF trace to a pure-protocol `black_box` — the 9 Air searchFlight case

[English](case-study.md) | [中文](case-study.zh-CN.md)

This is the redacted write-up of how I went from a WeChat mini-program flight
search (`/thirdpart/res/wx/mina/searchFlight` on `api.9air.com`) to a standalone
client that issues its own Tongdun device fingerprint and signs its own requests
— no WMPF, no WebView, no browser.

The app id and every live credential in this document are redacted. The
algorithmic findings are the reusable part and are reproduced in `tdbox/` and
`js/`.

---

## One-line chain

```
searchFlight trace
  -> architecture split (AppService / page-frame)
  -> header sign = MD5("wx-mini" + "wx-minkey" + timestamp)
  -> query = encodeURIComponent(JSON.stringify()) + inner sign
  -> validation matrix: only black_box + inner sign are actually checked
  -> 2.1.4 WASM path rejects forged profiles ("074")
  -> version rollback to 1.7.7 (pure JS, no canvas/WebGL check)
  -> tokenId -> black_box transform reconstructed
  -> pure-protocol client, no WebView
```

---

## The target

The 9 Air mini-program's flight search is an ordinary JSON POST:

```
POST https://api.9air.com/thirdpart/res/wx/mina/searchFlight
```

The body carries the search criteria plus an `Anti-Headers` blob, and the
request headers carry `sign`, `timestamp`, `x-s3-sid`, `x-sw-token` and
`black_box`. `black_box` is the Tongdun device fingerprint, and it is the field
that actually blocks a naive replay.

The whole client runs in two WeChat runtimes:

| Runtime | Role |
|---|---|
| AppService | business logic; calls `setBlackBox(black_box)` |
| page-frame (WebView) | render layer; *not* where the signing happens |

The first mistake to avoid is assuming the device fingerprint lives in the
WebView. It is set from AppService, which is what the WMPF trace shows.

---

## Round 1 — one trace, two halves

I captured the request with a WMPF trace. Two things matter for anything that
follows:

1. The trace is a **snapshot of the current app version**, which (as it turns
   out later) is already on the *new* Tongdun SDK. Nothing you do to the trace
   can turn a 2.1.4 request into a 1.7.7 one.
2. The request URL, headers and body are all visible, but the `black_box` is a
   value the SDK produced *upstream*, in AppService, before the network call.
   The trace shows the result, not the derivation.

The first genuinely useful artifact from the trace was the header signing.

## Round 2 — header sign is a one-liner MD5

The `sign` header was the easiest to reproduce. It is:

```
sign = MD5("wx-mini" + "wx-minkey" + timestamp).toUpperCase()
```

where `timestamp` is `YYYY-MM-DD HH:mm:ss` in Beijing time. Reproduced in
`tdbox/sign.py::header_sign`, and the reference MD5 check (`md5('')` =
`D41D8CD98F00B204E9800998ECF8427E`) passes in `js/sign_driver.js` before any
signing is attempted.

## Round 3 — query encoding, then the inner sign

The `Anti-Headers` blob contains a `query` field that is *double-encoded*:
each value is first `JSON.stringify`-ed, then `encodeURIComponent`-ed. So a
string value `"CAN"` becomes `%22CAN%22` — the surrounding quotes survive.

The inner sign (`Anti-Headers.sign`) is `FMAgent().sign({ path, query })` from
the Tongdun SDK, 168 chars in the 1.7.x path. This is the part that genuinely
requires running the SDK — there is no pure-Python shortcut for it, so the
repository runs the original SDK inside SpiderMonkey (`js/sign_driver.js`).

## Round 4 — the validation matrix

The decisive experiment was to break one field at a time and see what the
server rejects. This is what actually matters, and it is easy to get backwards:

| Field | Actually validated? |
|---|---|
| `black_box` | **yes** — the fingerprint gate |
| inner sign (`Anti-Headers.sign`) | **yes** |
| `openid` | no |
| `x-s3-sid` / `x-sw-token` | no |

So the `sid`/`sw-token` pair (reconstructed in `tdbox/session.py` as base61 +
XOR checksum) exists for protocol completeness but is *not* the thing that
blocks a replay. The `black_box` is.

## Round 5 — the `074` wall

The naive first attempt was to replay the trace's `black_box` values. That
worked once, but a *fresh* profile was needed for a real standalone client, and
that is where it died.

The current SDK is `sdk/fm-2.1.4P-es`. Its profile upload goes to
`cn-fp.apitd.net/wxapp/v1`, and it performs strong canvas/WebGL validation. A
mocked host fails that check and the endpoint returns the `074` "data forgery"
error. This is the point where most people keep hammering the same wall — I
stopped and changed version instead.

## Round 6 — the SDK gives itself away

`apitd` is the interesting domain. Working through the new SDK's request fields
made the validation explicit rather than guessed:

- one field (`074`) is a **plaintext authenticity check of the device info** —
  it is not derived, it is compared;
- another (`K`) is **random**, so it cannot be the thing being validated.

This is the "mid-point self-check" in the write-up: I ran an A/B test (present
vs. absent fields) and confirmed `K` is random, which rules it out as a
deterministic gate. The conclusion is that *faking the device info to satisfy
the 2.1.4 check is not feasible* — the check is designed to reject exactly that.

## A different track — version rollback

The module name `sdk/fm-2.1.4P-es` is itself a signal: `2.1.4` implies a
historical `fm-1.x`, and the *new* build is the one doing strong validation.

The 1.7.7 generation is pure JS, uploads to `fp.tongdun.net/wxapp/profile.json`,
and has **no** canvas/WebGL validation. Put it in the same mocked host and the
endpoint returns `code=000` with a fresh `tokenId`. That is the entire trick:
don't fight the 2.1.4 check, use the version that never had it.

To be precise about provenance: the architecture split, the header sign, the
query encoding, the validation matrix and the first trace-replay client were
reconstructed independently. The 1.7.7 rollback and the Tongdun loop were landed
and verified after obtaining the 1.7.7 SDK and an existing reference
implementation — not invented from scratch.

## Final step — the transform

Once a `tokenId` is issued, the `black_box` is a local, non-cryptographic
transform. De-obfuscating the 1.7.7 SDK gives exactly this:

```js
function L(n) {
    var t = n.charAt(0);
    var r = "ghijklmnopqrstuv".charAt("0123456789abcdef".indexOf(t));
    return F(F(F(n.replace(t, r), 4), 15), 24);
}
```

`F(s, i)` inserts one random base62 char at index `i`. So:

1. the `tokenId` must be 23 chars and start/end with a hex char;
2. map the first char `0123456789abcdef` -> `ghijklmnopqrstuv`;
3. insert a random base62 char at ascending indexes 4, 15, 24 -> 26 chars.

This is `tdbox/transform.py::token_id_to_black_box`, and it round-trips against
the SDK's own `Z()` in `js/token_driver.js`. The test suite covers the mapping,
the insertion slots, the length contract and the rejection of non-hex tokens.

## Result

A standalone client now:

1. issues its own `tokenId` (1.7.7 SDK in SpiderMonkey, POST via Necko),
2. transforms it to `black_box` in pure Python,
3. signs the header (MD5) and the body (inner `FMAgent.sign`),
4. submits the search and parses flights.

The pure-Python layer is fully unit-tested (16 tests, no runtime deps); the
SpiderMonkey/Necko orchestration is recorded from the original working run.

## Honest boundaries

- The 1.7.x path is the **weak** one. The 2.1.x WASM path is **not** bypassed
  here — the whole point of the rollback is to avoid it.
- The device-fingerprint *forgery* against 2.1.4 is infeasible; that conclusion
  is the reason the project took the version-rollback route.
- The `sid`/`sw-token` reconstruction is for protocol completeness; those fields
  are not validated by the target and are not load-bearing.

## Retrospective

The real turning points were three, and they are transferable:

1. **Break one variable at a time.** The validation matrix (which field blocks,
   which doesn't) is the highest-value result and it came from single-variable
   negative tests, not from reading code.
2. **The version number is a hint.** "2.1.4" implied "1.x exists"; the strong
   validation was a property of the *latest* version, not of the product.
3. **Don't fight the strong check — check whether a weaker version is still
   accepted.** Weak endpoints that were never turned off are the single most
   reusable lesson here.

If you are doing the same thing on another mini-program: trace the request,
split the runtimes, reproduce the cheap signing first, then find which *one*
field is actually the gate before you spend any time on the device fingerprint.
