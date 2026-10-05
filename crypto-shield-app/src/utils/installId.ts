// A random identifier minted once per INSTALL and kept in SecureStore.
//
// Its only job is to bound the one free exposure check per install (see
// handle_free_exposure_check in relayshield_api.py). It is never sent by the
// funnel counters (src/utils/analytics.ts) and never combined with the email:
// the server stores only a one-way hash of it.
//
// SecureStore does not survive an uninstall, so a reinstall is a new install and
// gets a fresh allowance. That is accepted: the real bound on abuse is the
// server's global daily cap, not this id.
import * as SecureStore from "expo-secure-store";

const INSTALL_ID_KEY = "cs_install_id";
let memo: string | null = null;

function randomUuid(): string {
  // react-native-get-random-values is imported first in App.tsx (via
  // src/polyfills.ts), which is what makes crypto.getRandomValues exist here.
  const bytes = new Uint8Array(16);
  (globalThis as any).crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
  const h = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export async function getInstallId(): Promise<string> {
  if (memo) return memo;
  try {
    const stored = await SecureStore.getItemAsync(INSTALL_ID_KEY);
    if (stored && stored.length >= 16) { memo = stored; return stored; }
  } catch {
    // fall through and mint one
  }
  const fresh = randomUuid();
  try { await SecureStore.setItemAsync(INSTALL_ID_KEY, fresh); } catch { /* in-memory only */ }
  memo = fresh;
  return fresh;
}
