// Anonymous funnel counters, and the single place the distribution channel is
// named.
//
// WHY THIS EXISTS. Stripe sees only COMPLETED trials, so at near-zero volume it
// cannot say whether nobody reaches the paywall or everybody reaches it and
// declines, and those two need opposite fixes. These four counters answer that.
//
// NO IDENTIFIER OF ANY KIND IS SENT: not the install id, not the push token, not
// the email, not the wallet. The server accepts only an allow-listed event name
// plus three short [a-z0-9_.-] tags and writes one log line. See handle_app_event
// in relayshield_api.py and the privacy policy's "Usage counters" paragraph.
//
// Never throws, never blocks the UI, and a failed send is simply lost.
import Constants from "expo-constants";

// The Solana dApp Store build. A Google Play build changes THIS and the two
// client_reference_id values in PaywallScreen.tsx, nowhere else
// (test_cs_mobile_free_check.py fails if those drift apart).
export const CHANNEL = "solana";

export type AppEvent =
  | "paywall_viewed"
  | "checkout_tapped"
  | "wallet_connected"
  | "onboarding_completed";

const RS_BASE = "https://api.relayshield.net";

export function track(event: AppEvent, ctx: string = ""): void {
  try {
    const version = String(Constants.expoConfig?.version ?? "");
    const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), 4000) : null;
    fetch(`${RS_BASE}/v1/app/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, ctx, version, platform: CHANNEL }),
      signal: ctrl?.signal,
    })
      .catch(() => {})
      .finally(() => { if (timer) clearTimeout(timer); });
  } catch {
    // a counter must never be the reason the app misbehaves
  }
}
