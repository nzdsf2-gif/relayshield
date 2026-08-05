import { useEffect } from "react";
import { Linking, Alert } from "react-native";
import { linkCryptoShieldSubscriptionBySession } from "../api/relayshield";

// Catches the deep link Stripe's Checkout success page redirects into after
// a Crypto Shield Mobile Pro purchase (net.relayshield.cryptoshieldmobile://unlock?session_id=...)
// and auto-provisions the API key with zero manual entry. Handles both the
// cold-start case (app opened fresh by the link) and the already-running case.
export function useSubscriptionDeepLink(saveApiKey: (key: string) => Promise<void>) {
  useEffect(() => {
    async function handleUrl(url: string | null) {
      if (!url) return;
      // Avoid the global URL/URLSearchParams API -- not reliably available
      // in this Hermes/RN version and this project has no polyfill for it.
      // Expected shape: net.relayshield.cryptoshieldmobile://unlock?session_id=xxx
      if (!/:\/\/unlock(\?|$)/.test(url)) return;
      const match = url.match(/[?&]session_id=([^&]+)/);
      const sessionId = match ? decodeURIComponent(match[1]) : null;
      if (!sessionId) return;

      try {
        const key = await linkCryptoShieldSubscriptionBySession(sessionId);
        await saveApiKey(key);
        Alert.alert("You're all set", "Your Crypto Shield Pro subscription is linked — live scans are unlocked.");
      } catch (err: any) {
        Alert.alert(
          "Almost there",
          "We couldn't confirm your subscription yet — it may still be processing. " +
          "Open Settings and enter your checkout email to finish linking, or try again in a moment.",
        );
      }
    }

    Linking.getInitialURL().then(handleUrl);
    const sub = Linking.addEventListener("url", ({ url }) => handleUrl(url));
    return () => sub.remove();
  }, [saveApiKey]);
}
