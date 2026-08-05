// Required before any @solana/web3.js or Mobile Wallet Adapter import —
// React Native has neither Buffer nor a real crypto.getRandomValues.
// Must be imported as the very first line of App.tsx.
import "react-native-get-random-values";
import { Buffer } from "buffer";

if (typeof global.Buffer === "undefined") {
  global.Buffer = Buffer;
}
