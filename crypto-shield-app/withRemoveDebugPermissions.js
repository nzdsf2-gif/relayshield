const { withAndroidManifest } = require("@expo/config-plugins");

// React Native's own debug-only manifest fragment (react-native/ReactAndroid/src/debug/AndroidManifest.xml)
// declares SYSTEM_ALERT_WINDOW for dev-mode overlay tools (error screen, dev menu). It's meant to be
// scoped to debug builds only, but Expo/React Native release builds are known to leak it through
// regardless (documented: expo/expo#8942). Crypto Shield never uses this permission for anything —
// it's flagged as "sensitive" by app store review (overlay/tapjacking risk) with no legitimate use to
// point to, so explicitly strip it via tools:node="remove" in the merged manifest.
const REMOVE_PERMISSIONS = ["android.permission.SYSTEM_ALERT_WINDOW"];

module.exports = function withRemoveDebugPermissions(config) {
  return withAndroidManifest(config, (config) => {
    const manifest = config.modResults.manifest;
    manifest.$["xmlns:tools"] = "http://schemas.android.com/tools";

    if (!manifest["uses-permission"]) {
      manifest["uses-permission"] = [];
    }

    for (const permission of REMOVE_PERMISSIONS) {
      // A plain <uses-permission> entry for this permission also lands in
      // our OWN primary manifest (not just contributed by a merged-in
      // library later). An explicit plain declaration in the primary
      // manifest always wins over a sibling tools:node="remove" entry in
      // that SAME file — the remove directive only suppresses
      // contributions from OTHER (merged-in) manifests, so leaving the
      // plain entry in place here defeated the fix entirely. Strip any
      // plain entries first, then add exactly one remove-tagged entry.
      manifest["uses-permission"] = manifest["uses-permission"].filter(
        (p) => !(p.$["android:name"] === permission && p.$["tools:node"] !== "remove")
      );

      const removeTagAlreadyPresent = manifest["uses-permission"].some(
        (p) => p.$["android:name"] === permission && p.$["tools:node"] === "remove"
      );
      if (!removeTagAlreadyPresent) {
        manifest["uses-permission"].push({
          $: { "android:name": permission, "tools:node": "remove" },
        });
      }
    }

    return config;
  });
};
