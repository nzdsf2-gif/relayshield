const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// Expo SDK 51 disables package-exports resolution by default (it only
// became default-on in SDK 52). @solana-mobile/mobile-wallet-adapter-protocol
// declares a correct "./encoding" subpath in its "exports" map (resolving to
// lib/cjs/encoding.native.js), but that mapping is invisible to Metro's
// classic/legacy resolution, which only looks for a root-level encoding.js
// that doesn't exist. Enabling exports resolution lets Metro see it.
config.resolver.unstable_enablePackageExports = true;

module.exports = config;
