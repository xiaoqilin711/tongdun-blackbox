'use strict';

// SpiderMonkey driver: run the SDK's own Z(tokenId) transform and return the
// resulting 26-char black_box. This is the "official" reference path; the
// pure-Python equivalent lives in tdbox/transform.py and is cross-checked
// against this driver.

var input = JSON.parse(scriptArgs[0]);
var runtime = BrowserEnvSpiderMonkey.createSpiderMonkeyRuntime({
  mode: 'production',
  profile: input.profile,
  manifest: input.manifest
});

var tokenId = String(input.tokenId || '');
if (tokenId.length !== 23) throw new Error('unexpected tokenId length: ' + tokenId.length);

var blackBox = Z(tokenId);
if (blackBox.length !== 26) throw new Error('unexpected black_box length: ' + blackBox.length);

runtime.assertProductionClean();
print(JSON.stringify({
  status: 'blackbox-ready',
  tokenId: tokenId,
  blackBox: blackBox,
  tokenIdLength: tokenId.length,
  blackBoxLength: blackBox.length,
  manifest: runtime.manifest()
}));
