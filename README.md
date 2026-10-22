# tdbox — Tongdun `black_box` reverse-engineering study

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/xiaoqilin711/tongdun-blackbox/actions/workflows/ci.yml/badge.svg)](https://github.com/xiaoqilin711/tongdun-blackbox/actions/workflows/ci.yml)

Pure-protocol recreation of the Tongdun (FraudMetrix / 同盾) device-fingerprint
`black_box` transform and the surrounding app-layer signing, plus a **redacted**
9 Air mini-program flight-search case study.

The point of this repository is the *reusable layer*: you can turn a fresh
Tongdun `tokenId` into a valid `black_box` in pure Python, without running the
device-fingerprint SDK and without a WMPF/WebView session. The 9 Air case study
exists only to prove the pieces work end-to-end against a real target.

---

## What problem this solves

Mini-programs that integrate Tongdun's device fingerprint carry a `black_box`
field on business requests. It is produced by the SDK from a `tokenId` issued by
`fp.tongdun.net/wxapp/profile.json`, and the SDK has two very different
generations:

| Generation | Form | Validation | Result |
|---|---|---|---|
| 1.7.x (old) | pure JS | weak — no canvas/WebGL check | `code=000`, issues `tokenId` |
| 2.1.x (new) | WASM plugin | strong canvas/WebGL validation | rejects "forged" profiles (`074`) |

The `tokenId → black_box` transform is *not* cryptographic. It is a fixed
character mapping plus three random insertions, which is what this repository
re-implements in `tdbox/transform.py`.

## What's inside

```
tdbox/                    generic library (pure Python, no SDK bundled)
├── transform.py          tokenId -> black_box (the Z transform)
├── sign.py               header MD5 sign + encodeURIComponent(JSON.stringify)
├── session.py            base61 + XOR-checksum sid / sw-token
└── cli.py                transform / validate / sign / encode
js/                       SpiderMonkey drivers (run the original SDK paths)
├── profile_driver.js     capture the profile.json request the SDK would send
├── token_driver.js       run the SDK's own Z() as a cross-check reference
└── sign_driver.js        run FMAgent.sign() for the inner sign
examples/                 redacted end-to-end case study
├── generate_blackbox.py  fresh black_box via SpiderMonkey + Firefox Necko
├── nineair_search.py     9 Air searchFlight pure-protocol client
├── host-inputs.example.json
└── profile.example.json
scripts/
└── extract_material.py   pull the Tongdun SDK out of your own plugin source
tests/                    unittest suite for the pure-Python logic
docs/
├── case-study.md         redacted walkthrough (English)
└── case-study.zh-CN.md   redacted walkthrough (Chinese)
```

## Quick start

The pure-Python layer has **zero** runtime dependencies — no SDK, no
SpiderMonkey, no browser. Install and try it immediately:

```bash
pip install -e .

# run the tests
python -m unittest discover -s tests -v

# transform a 23-char tokenId into a 26-char black_box
python -m tdbox.cli transform 2b2b2b2b2b2b2b2b2b2b2b2 --seed 1

# verify a black_box against its tokenId
python -m tdbox.cli validate 2b2b2b2b2b2b2b2b2b2b2b2 ib2bI2b2b2b2b2bk2b2b2b2b22

# header sign = MD5(prefix + key + timestamp)
python -m tdbox.cli sign wx-mini wx-minkey "2026-10-22 12:00:00"

# encodeURIComponent(JSON.stringify()) per field
python -m tdbox.cli encode '{"a":"CAN","b":[1,2]}'
```

Sample outputs (real, from this repo):

```
$ python -m tdbox.cli transform 2b2b2b2b2b2b2b2b2b2b2b2 --seed 1
ib2bI2b2b2b2b2bk2b2b2b2b22

$ python -m tdbox.cli sign wx-mini wx-minkey "2026-10-22 12:00:00"
9D5E9264AB02E7B167C42A64C8AB7517

$ python -m tdbox.cli encode '{"a":"CAN"}'
{"a": "%22CAN%22"}
```

## Full reproduction (SpiderMonkey + Necko)

The pure-Python helpers cover the *transform and signing math*. To actually
**issue** a fresh `tokenId` (i.e. make the Tongdun endpoint accept you), you must
run the 1.7.x SDK inside a mocked mini-program host. That part needs the
xiaojianbang runtime set and your own SDK extract:

1. **Extract the SDK** from your own plugin package (never committed here):
   ```bash
   python scripts/extract_material.py <plugin-source.js> \
     --line <sdk-line> --output material/tdfp_fm_1.7.7.js
   ```
2. **Generate a black_box** (SpiderMonkey for the SDK + Necko for the POST):
   ```bash
   python examples/generate_blackbox.py --json-out out/blackbox.json
   ```
3. **Run the search** (uses `FMAgent.sign` for the inner sign):
   ```bash
   python examples/nineair_search.py \
     --departure CAN --arrival BJS --depart-date 2026-10-25 \
     --openid <your-openid> --json-out out/search.json
   ```

The runtime roots are configurable via `XJB_BROWSER_ENV`, `XJB_FIREFOX_JS_RUNTIME`,
`XJB_NECKO_RUNTIME` (defaults point at a local `C:\mozilla-build-outputs\releases`).

## Architecture

```
        tokenId (23)                         request body
             │                                    │
             ▼                                    ▼
   ┌─────────────────────┐            ┌────────────────────────┐
   │  tdbox.transform     │            │  tdbox.sign            │
   │  Z(): map + 3 insert │            │  header MD5 sign       │
   │        │             │            │  encodeURIComponent    │
   │        ▼             │            └────────────────────────┘
   │  black_box (26)      │                     │
   └─────────────────────┘                     │
             │                                  │
             └──────────────┬───────────────────┘
                            ▼
              SpiderMonkey (FMAgent.sign)  ──►  Firefox Necko  ──►  target API
              (inner sign, 168 chars)             (same-session POST)
```

## Honest boundaries

- **What is re-implemented here**: the `tokenId → black_box` transform, the
  header MD5 sign, the query encoding, and the `sid`/`sw-token` construction —
  all verified against real artifacts.
- **What is *not* included**: the Tongdun SDK source (`material/` is
  git-ignored — extract it yourself with `scripts/extract_material.py`), and any
  live session material (`out/`, real `openid`, real `black_box`). The app id in
  the examples is redacted.
- **What was not end-to-end verified here**: the `nineair_search.py` flow depends
  on the xiaojianbang runtime being present on the machine; the pure-Python layer
  is fully tested, but the SpiderMonkey/Necko orchestration is documented from the
  original working run, not re-executed in CI.
- The 1.7.x path is the *weak* one. The 2.1.x WASM path is **not** bypassed here;
  see the case study for why.

## Case study

The full "problem → dead ends → version rollback → working protocol" story is in
[docs/case-study.md](docs/case-study.md) (English) /
[docs/case-study.zh-CN.md](docs/case-study.zh-CN.md) (中文).

## License

[MIT](LICENSE)
