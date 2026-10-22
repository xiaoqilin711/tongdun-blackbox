'use strict';

// SpiderMonkey driver: run FMAgent.getInfo() inside a mocked wx host, capture
// the profile.json request the SDK is about to send, and hand it back to the
// Python orchestrator (which performs the actual HTTP call via Necko).
//
// Load order: [browser-env core.js, spidermonkey adapter, <extracted SDK>, this file]
//
// The Tongdun SDK source is NOT redistributed in this repository. Extract it
// from your own plugin package with scripts/extract_material.py.

var input = JSON.parse(scriptArgs[0]);
var host = input.hostInputs;
if (!host || host.schema !== 'host-inputs-v1') throw new Error('explicit hostInputs required');

function hostValue(name) {
  if (!Object.prototype.hasOwnProperty.call(host, name)) throw new Error('missing host input: ' + name);
  return JSON.parse(JSON.stringify(host[name]));
}

var runtime = BrowserEnvSpiderMonkey.createSpiderMonkeyRuntime({
  mode: 'production',
  profile: input.profile,
  manifest: input.manifest
});

var storage = Object.create(null);
var capturedRequest = null;
var timerSequence = 0;
var timers = Object.create(null);

globalThis.setTimeout = function (callback, delay) {
  var id = ++timerSequence;
  timers[id] = { callback: callback, delay: Number(delay) || 0 };
  return id;
};
globalThis.clearTimeout = function (id) { delete timers[id]; };

function callbackResult(options, result, failed) {
  var callback = failed ? options && options.fail : options && options.success;
  if (typeof callback === 'function') callback(result);
  if (typeof (options && options.complete) === 'function') options.complete(result);
}

function systemInfo() { return hostValue('systemInfo'); }

globalThis.wx = {
  env: { USER_DATA_PATH: '/usr' },
  getStorageSync: function (key) {
    return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : '';
  },
  setStorageSync: function (key, value) { storage[key] = value; },
  getStorage: function (options) {
    callbackResult(options, { errMsg: 'getStorage:ok', data: storage[options.key] || '' }, false);
  },
  setStorage: function (options) {
    storage[options.key] = options.data;
    callbackResult(options, { errMsg: 'setStorage:ok' }, false);
  },
  getSystemInfoSync: systemInfo,
  getDeviceInfo: function () { return hostValue('deviceInfo'); },
  getLaunchOptionsSync: function () { return hostValue('launchOptions'); },
  getAccountInfoSync: function () { return hostValue('accountInfo'); },
  getNetworkType: function (options) { callbackResult(options, hostValue('networkType'), false); },
  startWifi: function (options) { callbackResult(options, hostValue('startWifi'), true); },
  stopWifi: function () { return Promise.resolve(hostValue('stopWifi')); },
  getConnectedWifi: function (options) { callbackResult(options, hostValue('connectedWifi'), true); },
  getScreenBrightness: function (options) { callbackResult(options, hostValue('brightness'), false); },
  request: function (options) {
    capturedRequest = {
      url: String(options.url || ''),
      method: String(options.method || 'GET'),
      timeout: Number(options.timeout || 0),
      header: JSON.parse(JSON.stringify(options.header || {})),
      data: JSON.parse(JSON.stringify(options.data || {}))
    };
    return undefined;
  }
};

var agent = new FMAgent({
  partnerCode: input.partnerCode,
  appName: input.appName,
  env: 'PRODUCTION'
});
agent.getInfo({
  mode: 'plugin',
  openid: input.openid || 'anonymous',
  unionid: input.unionid || '',
  getInfoType: '2',
  timeout: 5000,
  success: function () {},
  fail: function () {}
});

for (var turn = 0; turn < 100 && !capturedRequest; turn++) {
  if (typeof drainJobQueue === 'function') drainJobQueue();
}
if (!capturedRequest) throw new Error('FMAgent did not reach wx.request');
if (!/^https:\/\/fp\.tongdun\.net\/wxapp\/profile\.json\?partner=/.test(capturedRequest.url)) {
  throw new Error('unexpected Tongdun endpoint: ' + capturedRequest.url);
}

runtime.assertProductionClean();
print(JSON.stringify({
  status: 'profile-ready',
  request: capturedRequest,
  storage: storage,
  pendingTimers: Object.keys(timers).length,
  manifest: runtime.manifest()
}));
