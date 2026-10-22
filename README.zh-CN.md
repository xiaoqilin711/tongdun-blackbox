# tdbox — 同盾 `black_box` 逆向研究

[English](README.md) | [中文](README.zh-CN.md)

纯协议复现同盾（FraudMetrix / 顶象）设备指纹 `black_box` 的转换逻辑，以及配套的应用层签名，并附一个**已脱敏**的九元航空小程序航班搜索案例。

这个仓库的核心价值在**可复用的通用层**：你可以用纯 Python 把一个新鲜的同盾 `tokenId` 转成合法的 `black_box`，不需要跑设备指纹 SDK，也不需要 WMPF/WebView 会话。九元案例只是用来证明这套东西能端到端跑在真实目标上。

---

## 它解决什么问题

集成了同盾设备指纹的小程序，业务请求上会带一个 `black_box` 字段。它由 SDK 从 `fp.tongdun.net/wxapp/profile.json` 下发的 `tokenId` 转换而来，而 SDK 有两代差异巨大的实现：

| 代际 | 形态 | 校验 | 结果 |
|---|---|---|---|
| 1.7.x（旧） | 纯 JS | 弱——无 canvas/WebGL 校验 | `code=000`，下发 `tokenId` |
| 2.1.x（新） | WASM 插件 | 强 canvas/WebGL 校验 | 拒绝"伪造"的 profile（`074`） |

`tokenId → black_box` 的转换**不是密码学**。它是一次固定的字符映射加三次随机插入，本仓库把它复现到了 `tdbox/transform.py`。

## 目录结构

```
tdbox/                    通用库（纯 Python，不捆绑 SDK）
├── transform.py          tokenId -> black_box（Z 变换）
├── sign.py               header MD5 签名 + encodeURIComponent(JSON.stringify)
├── session.py            base61 + XOR 校验的 sid / sw-token
└── cli.py                transform / validate / sign / encode
js/                       SpiderMonkey 驱动（跑原始 SDK 路径）
├── profile_driver.js     捕获 SDK 即将发出的 profile.json 请求
├── token_driver.js       跑 SDK 自己的 Z() 作为交叉校验参考
└── sign_driver.js        跑 FMAgent.sign() 生成内层签名
examples/                 已脱敏的端到端案例
├── generate_blackbox.py  通过 SpiderMonkey + Firefox Necko 生成新鲜 black_box
├── nineair_search.py     九元 searchFlight 纯协议客户端
├── host-inputs.example.json
└── profile.example.json
scripts/
└── extract_material.py   从你自己的插件源码里抽出同盾 SDK
tests/                    纯 Python 逻辑的 unittest 套件
docs/
├── case-study.md         脱敏复盘（英文）
└── case-study.zh-CN.md   脱敏复盘（中文）
```

## 快速开始

纯 Python 层**零运行时依赖**——不需要 SDK、不需要 SpiderMonkey、不需要浏览器。装完立刻能跑：

```bash
pip install -e .

# 跑测试
python -m unittest discover -s tests -v

# 把 23 位 tokenId 转成 26 位 black_box
python -m tdbox.cli transform 2b2b2b2b2b2b2b2b2b2b2b2 --seed 1

# 用 tokenId 校验一个 black_box
python -m tdbox.cli validate 2b2b2b2b2b2b2b2b2b2b2b2 ib2bI2b2b2b2b2bk2b2b2b2b22

# header sign = MD5(prefix + key + timestamp)
python -m tdbox.cli sign wx-mini wx-minkey "2026-10-22 12:00:00"

# 每个字段做 encodeURIComponent(JSON.stringify())
python -m tdbox.cli encode '{"a":"CAN","b":[1,2]}'
```

真实输出示例（本仓库实测）：

```
$ python -m tdbox.cli transform 2b2b2b2b2b2b2b2b2b2b2b2 --seed 1
ib2bI2b2b2b2b2bk2b2b2b2b22

$ python -m tdbox.cli sign wx-mini wx-minkey "2026-10-22 12:00:00"
9D5E9264AB02E7B167C42A64C8AB7517

$ python -m tdbox.cli encode '{"a":"CAN"}'
{"a": "%22CAN%22"}
```

## 完整复现（SpiderMonkey + Necko）

纯 Python 层覆盖的是**转换与签名的数学**。要真正**签发**一个新鲜 `tokenId`（也就是让同盾端点接受你），必须让 1.7.x SDK 跑在模拟的小程序宿主里。这一步需要 xiaojianbang 运行时和你自己提取的 SDK：

1. **提取 SDK**（从你自己的插件包里，本仓库从不提交 SDK 源码）：
   ```bash
   python scripts/extract_material.py <plugin-source.js> \
     --line <sdk-line> --output material/tdfp_fm_1.7.7.js
   ```
2. **生成 black_box**（SpiderMonkey 跑 SDK + Necko 发 POST）：
   ```bash
   python examples/generate_blackbox.py --json-out out/blackbox.json
   ```
3. **跑搜索**（用 `FMAgent.sign` 生成内层签名）：
   ```bash
   python examples/nineair_search.py \
     --departure CAN --arrival BJS --depart-date 2026-10-25 \
     --openid <你的-openid> --json-out out/search.json
   ```

运行时根目录可用 `XJB_BROWSER_ENV`、`XJB_FIREFOX_JS_RUNTIME`、`XJB_NECKO_RUNTIME`
配置（默认指向本机 `C:\mozilla-build-outputs\releases`）。

## 架构

```
        tokenId (23)                         请求体
             │                                  │
             ▼                                  ▼
   ┌─────────────────────┐            ┌────────────────────────┐
   │  tdbox.transform     │            │  tdbox.sign            │
   │  Z()：映射 + 3 次插入 │            │  header MD5 签名       │
   │        │             │            │  encodeURIComponent    │
   │        ▼             │            └────────────────────────┘
   │  black_box (26)      │                     │
   └─────────────────────┘                     │
             │                                  │
             └──────────────┬───────────────────┘
                            ▼
              SpiderMonkey (FMAgent.sign)  ──►  Firefox Necko  ──►  目标 API
              （内层签名，168 位）                （同会话 POST）
```

## 诚实边界

- **本仓库复现了什么**：`tokenId → black_box` 转换、header MD5 签名、query 编码、`sid`/`sw-token` 构造——都对照真实产物验证过。
- **没有包含什么**：同盾 SDK 源码（`material/` 已 git-ignore，用 `scripts/extract_material.py` 自己提取），以及任何有效会话材料（`out/`、真实 `openid`、真实 `black_box`）。示例里的 AppID 已打码。
- **这里没有端到端验证的路径**：`nineair_search.py` 依赖本机有 xiaojianbang 运行时；纯 Python 层有完整测试，但 SpiderMonkey/Necko 编排是按原始成功运行记录整理的，没有在 CI 里重跑。
- 1.7.x 是**弱**的那条路。2.1.x 的 WASM 路径这里**没有**绕过；原因见 case-study。

## 案例复盘

完整的"问题 → 死路 → 版本回溯 → 跑通协议"过程见 [docs/case-study.md](docs/case-study.md)（英文）/
[docs/case-study.zh-CN.md](docs/case-study.zh-CN.md)（中文）。

## License

[MIT](LICENSE)
