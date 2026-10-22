# 从 WMPF trace 到纯协议 `black_box`——九元航空 searchFlight 案例

[English](case-study.md) | [中文](case-study.zh-CN.md)

这是我把一个微信小程序航班搜索（`api.9air.com` 的 `/thirdpart/res/wx/mina/searchFlight`）从抓包一路做到独立客户端的脱敏复盘：自己签发同盾设备指纹、自己签请求，不用 WMPF、不用 WebView、不用浏览器。

本文中的 AppID 和所有有效凭据都已打码。算法结论是可复用的部分，已复现到 `tdbox/` 和 `js/`。

---

## 一句话链路

```
searchFlight trace
  -> 架构分层（AppService / page-frame）
  -> header sign = MD5("wx-mini" + "wx-minkey" + timestamp)
  -> query = encodeURIComponent(JSON.stringify()) + 内层 sign
  -> 校验矩阵：只有 black_box + 内层 sign 真正被校验
  -> 2.1.4 WASM 路径拒绝伪造 profile（"074"）
  -> 版本回溯到 1.7.7（纯 JS，无 canvas/WebGL 校验）
  -> 还原 tokenId -> black_box 转换
  -> 纯协议客户端，无 WebView
```

---

## 目标

九元小程序的航班搜索是一个普通的 JSON POST：

```
POST https://api.9air.com/thirdpart/res/wx/mina/searchFlight
```

请求体带搜索条件加一个 `Anti-Headers` 块，请求头带 `sign`、`timestamp`、`x-s3-sid`、`x-sw-token` 和 `black_box`。`black_box` 是同盾设备指纹，也是真正挡住重放的那个字段。

整个客户端跑在微信的两个运行时里：

| 运行时 | 作用 |
|---|---|
| AppService | 业务逻辑；调用 `setBlackBox(black_box)` |
| page-frame（WebView） | 渲染层；**不是**签名发生的地方 |

第一个要避免的错误，就是以为设备指纹在 WebView 里。它是在 AppService 里设置的，WMPF trace 显示的正是这一点。

## 第一回合——一次 trace，两半

我用 WMPF trace 抓了请求。有两点对后面所有事都关键：

1. trace 是**当前应用版本的快照**，而（后面才发现）它已经在**新版**同盾 SDK 上了。你对 trace 做任何事，都不能把一个 2.1.4 的请求变成 1.7.7 的。
2. 请求 URL、头、体都看得见，但 `black_box` 是 SDK 在**上游**（AppService 里）生成的、网络调用之前的值。trace 显示的是结果，不是推导过程。

trace 里第一个真正有用的产物，是 header 签名。

## 第二回合——header sign 是一行 MD5

`sign` 头最容易复现。它就是：

```
sign = MD5("wx-mini" + "wx-minkey" + timestamp).toUpperCase()
```

其中 `timestamp` 是北京时间的 `YYYY-MM-DD HH:mm:ss`。复现在 `tdbox/sign.py::header_sign`，参考 MD5 校验（`md5('')` = `D41D8CD98F00B204E9800998ECF8427E`）在 `js/sign_driver.js` 里签名前先通过。

## 第三回合——query 编码，然后是内层 sign

`Anti-Headers` 块里有个 `query` 字段是**双重编码**的：每个值先 `JSON.stringify`，再 `encodeURIComponent`。所以字符串 `"CAN"` 变成 `%22CAN%22`——外层引号保留了下来。

内层 sign（`Anti-Headers.sign`）是同盾 SDK 的 `FMAgent().sign({ path, query })`，1.7.x 路径下是 168 位。这是真正需要跑 SDK 的部分——纯 Python 没有捷径，所以仓库在 SpiderMonkey 里跑原始 SDK（`js/sign_driver.js`）。

## 第四回合——校验矩阵

决定性的实验是**一次只破坏一个字段**，看服务端拒绝哪个。这才是真正重要的结论，而且很容易搞反：

| 字段 | 真的被校验了吗？ |
|---|---|
| `black_box` | **是**——指纹门 |
| 内层 sign（`Anti-Headers.sign`） | **是** |
| `openid` | 否 |
| `x-s3-sid` / `x-sw-token` | 否 |

所以 `sid`/`sw-token` 这对（在 `tdbox/session.py` 里还原成 base61 + XOR 校验）只是为了协议完整，**不是**挡住重放的东西。`black_box` 才是。

## 第五回合——撞上 `074` 的墙

天真的第一步是重放 trace 里的 `black_box` 值。这样能成功一次，但真正的独立客户端需要一个**新鲜** profile，于是就在这里死了。

当前 SDK 是 `sdk/fm-2.1.4P-es`。它的 profile 上传走 `cn-fp.apitd.net/wxapp/v1`，并且做了强 canvas/WebGL 校验。模拟宿主过不了这个检查，端点返回 `074` "数据伪造"错误。这是大多数人会继续撞同一堵墙的地方——我停下来，换了版本。

## 第六回合——SDK 自己招了

`apitd` 是有意思的域名。把新版 SDK 的请求字段走一遍，校验逻辑就从"猜"变成了"明摆着"：

- 一个字段（`074`）是**设备信息的明文真实性校验**——它不是推导出来的，是对比的；
- 另一个字段（`K`）是**随机**的，所以它不可能是被校验的那个。

这就是复盘里说的"中途自证"：我做了 A/B 对照（字段在 vs 字段不在），确认 `K` 是随机的，从而排除了它是确定性门。结论是：**伪造设备信息去满足 2.1.4 的检查不可行**——这个检查就是专门用来拒绝这种伪造的。

## 换一条思路——版本回溯

模块名 `sdk/fm-2.1.4P-es` 本身就是信号：`2.1.4` 意味着存在历史的 `fm-1.x`，而做强校验的是**最新**这个版本。

1.7.7 代是纯 JS，上传到 `fp.tongdun.net/wxapp/profile.json`，**没有** canvas/WebGL 校验。放进同一个模拟宿主，端点返回 `code=000` 加一个新鲜 `tokenId`。这就是全部诀窍：别去硬刚 2.1.4 的检查，用那个从来没有这个检查的版本。

关于来源要讲清楚：架构分层、header sign、query 编码、校验矩阵、以及第一版复用 trace 黑盒值的客户端，是我独立还原的；1.7.7 版本回溯和 tongdun 闭环，是拿到 1.7.7 旧版 SDK 和现成还原实现后落地验证的，不是从零发明。

## 最后一步——转换

一旦拿到 `tokenId`，`black_box` 就是一个本地的、非密码学的转换。反混淆 1.7.7 SDK 得到的就是这个：

```js
function L(n) {
    var t = n.charAt(0);
    var r = "ghijklmnopqrstuv".charAt("0123456789abcdef".indexOf(t));
    return F(F(F(n.replace(t, r), 4), 15), 24);
}
```

`F(s, i)` 在位置 `i` 插入一个随机 base62 字符。所以：

1. `tokenId` 必须 23 位，且首尾是十六进制字符；
2. 把首字符 `0123456789abcdef` -> `ghijklmnopqrstuv` 做映射；
3. 在升序位置 4、15、24 各插入一个随机 base62 字符 -> 26 位。

这就是 `tdbox/transform.py::token_id_to_black_box`，它能和 SDK 自己的 `Z()`（`js/token_driver.js`）互相往返。测试套件覆盖了映射、插入位置、长度约束和拒绝非十六进制 token。

## 结果

一个独立客户端现在能：

1. 自己签发 `tokenId`（SpiderMonkey 跑 1.7.7 SDK，Necko 发 POST），
2. 用纯 Python 把它转成 `black_box`，
3. 签 header（MD5）和 body（内层 `FMAgent.sign`），
4. 提交搜索并解析航班。

纯 Python 层有完整单元测试（16 个测试，零运行时依赖）；SpiderMonkey/Necko 编排按原始成功运行记录整理。

## 诚实边界

- 1.7.x 路径是**弱**的那条。2.1.x 的 WASM 路径这里**没有**绕过——回溯的整个目的就是绕开它。
- 针对 2.1.4 的设备指纹**伪造**不可行；这个结论正是本项目走版本回溯路线的原因。
- `sid`/`sw-token` 的还原是为了协议完整；这些字段目标并不校验，不是承重墙。

## 复盘

真正的转折点有三个，而且可以迁移：

1. **一次只变一个变量。** 校验矩阵（哪个字段挡、哪个不挡）是价值最高的结论，它来自单变量负例测试，不是读代码读出来的。
2. **版本号本身就是线索。** "2.1.4" 意味着 "1.x 存在"；强校验是**最新**版本的属性，不是产品本身的属性。
3. **别硬刚强校验——先确认更弱的版本是不是还接受。** 从没被关掉的弱接口，是这里最可复用的一条经验。

如果你在另一个小程序上做同样的事：抓请求、分层运行时、先把便宜的签名复现掉，然后在你花任何时间在设备指纹之前，先找出**哪一个**字段才是真正的门。
