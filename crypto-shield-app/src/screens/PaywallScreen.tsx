import React, { useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Linking, ActivityIndicator, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

// ── Stripe Payment Links (create in Stripe Dashboard → Payment Links) ──────────
// Replace these with real plink_ IDs from your Stripe dashboard.
const STRIPE_MONTHLY_URL = "https://buy.stripe.com/4gMdRa7Yq7OZf9aesn0Ny0g";
const STRIPE_ANNUAL_URL  = "https://buy.stripe.com/6oUdRabaC4CN4uwbgb0Ny0h";

interface Props {
  onClose?: () => void;
}

const FEATURES_PRO = [
  "5 monitored wallets",
  "Real-time push alerts",
  "Address poisoning detection",
  "SOL portfolio valuation",
  "EVM · Solana · TON · Bitcoin",
  "Criminal Telegram marketplace monitoring",
  "SIM-swap & breach alerts",
  "Security sweep (email + OAuth)",
];

export function PaywallScreen({ onClose }: Props) {
  const [loading, setLoading] = useState<"monthly" | "annual" | null>(null);

  async function openCheckout(plan: "monthly" | "annual") {
    const url = plan === "annual" ? STRIPE_ANNUAL_URL : STRIPE_MONTHLY_URL;
    setLoading(plan);
    try {
      const supported = await Linking.canOpenURL(url);
      if (!supported) throw new Error("Cannot open URL");
      await Linking.openURL(url);
    } catch {
      Alert.alert("Error", "Could not open checkout. Try again or visit pricing.relayshield.net");
    } finally {
      setLoading(null);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Header */}
        <View style={s.header}>
          <Text style={s.logo}>🛡</Text>
          <Text style={s.title}>Crypto Shield Pro</Text>
          <Text style={s.sub}>Real-time security for your Web3 wallets</Text>
          <View style={s.trialBadge}><Text style={s.trialBadgeText}>7 DAYS FREE — CANCEL ANYTIME</Text></View>
        </View>

        {/* Plans */}
        <View style={s.plans}>

          {/* Annual — highlighted */}
          <TouchableOpacity
            style={[s.planCard, s.planCardFeatured]}
            onPress={() => openCheckout("annual")}
            activeOpacity={0.85}
          >
            <View style={s.badgeRow}>
              <View style={s.badge}><Text style={s.badgeText}>BEST VALUE</Text></View>
              <Text style={s.savings}>Save 20%</Text>
            </View>
            <Text style={s.planPrice}>7 days free, then <Text style={s.planAmount}>$105.99</Text> / year</Text>
            <Text style={s.planPer}>That's $8.83 / month after trial — save 20%</Text>
            {loading === "annual"
              ? <ActivityIndicator color="#0a1628" style={{ marginTop: 14 }} />
              : <Text style={s.ctaFeatured}>Start Free Trial →</Text>}
          </TouchableOpacity>

          {/* Monthly */}
          <TouchableOpacity
            style={s.planCard}
            onPress={() => openCheckout("monthly")}
            activeOpacity={0.85}
          >
            <Text style={s.planPrice}>7 days free, then <Text style={s.planAmount}>$10.99</Text> / month</Text>
            <Text style={s.planPer}>No charge until day 8 — cancel anytime before then</Text>
            {loading === "monthly"
              ? <ActivityIndicator color="#00B5A5" style={{ marginTop: 14 }} />
              : <Text style={s.cta}>Start Free Trial →</Text>}
          </TouchableOpacity>
        </View>

        {/* Feature highlight cards */}
        <View style={s.highlights}>
          <HighlightCard icon="🛡" title="Wallet Risk Scans" desc="Instant risk scoring across EVM, Solana, TON, and Bitcoin wallets." />
          <HighlightCard icon="🔔" title="Real-time Push Alerts" desc="Get notified the moment a threat is detected — address poisoning, SIM-swap, breaches." />
          <HighlightCard icon="🖼" title="NFT Floor Alerts" desc="Track collections on Magic Eden, EVM, and TON. Alert when floor drops ≥15%." />
          <HighlightCard icon="📊" title="Portfolio Valuation" desc="Live SOL + SPL token portfolio value pulled securely from your wallets." />
          <HighlightCard icon="🕵️" title="Criminal Intel Feeds" desc="82+ monitored Telegram criminal marketplaces — continuously growing. Your data flagged before you know it's stolen." />
          <HighlightCard icon="🔐" title="Security Sweep" desc="Email breach, infostealer exposure, OAuth backdoors, and SIM-swap checks in one tap." />
        </View>

        {/* Footer links */}
        <View style={s.footer}>
          <TouchableOpacity onPress={() => Linking.openURL("https://terms.relayshield.net")}>
            <Text style={s.footerLink}>Terms</Text>
          </TouchableOpacity>
          <Text style={s.footerDot}> · </Text>
          <TouchableOpacity onPress={() => Linking.openURL("https://privacy.relayshield.net")}>
            <Text style={s.footerLink}>Privacy</Text>
          </TouchableOpacity>
        </View>

        {onClose && (
          <TouchableOpacity style={s.closeBtn} onPress={onClose}>
            <Text style={s.closeBtnText}>Maybe later</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:             { flex: 1, backgroundColor: "#0a1628" },
  scroll:           { padding: 24, paddingBottom: 40 },

  header:           { alignItems: "center", marginBottom: 28 },
  logo:             { fontSize: 52, marginBottom: 10 },
  title:            { fontSize: 26, fontWeight: "800", color: "#f1f5f9", textAlign: "center" },
  sub:              { fontSize: 13, color: "#64748b", marginTop: 6, textAlign: "center", lineHeight: 20 },
  trialBadge:       { marginTop: 12, backgroundColor: "#00B5A520", borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: "#00B5A5" },
  trialBadgeText:   { color: "#00B5A5", fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },

  plans:            { gap: 12, marginBottom: 28 },
  planCard:         { backgroundColor: "#0F1F3D", borderRadius: 16, padding: 20, borderWidth: 1, borderColor: "#1e3a5f" },
  planCardFeatured: { borderColor: "#00B5A5", borderWidth: 2 },

  badgeRow:         { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 10 },
  badge:            { backgroundColor: "#00B5A5", borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText:        { color: "#0a1628", fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
  savings:          { color: "#00B5A5", fontSize: 12, fontWeight: "700" },

  planPrice:        { fontSize: 15, color: "#94a3b8", fontWeight: "500" },
  planAmount:       { fontSize: 28, fontWeight: "800", color: "#f1f5f9" },
  planPer:          { fontSize: 11, color: "#475569", marginTop: 3 },

  ctaFeatured:      { marginTop: 14, backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 12, textAlign: "center", color: "#0a1628", fontWeight: "800", fontSize: 14, overflow: "hidden" },
  cta:              { marginTop: 14, borderWidth: 1, borderColor: "#00B5A5", borderRadius: 10, paddingVertical: 12, textAlign: "center", color: "#00B5A5", fontWeight: "700", fontSize: 14, overflow: "hidden" },

  comparison:       { flexDirection: "row", gap: 12, marginBottom: 28 },
  col:              { flex: 1, backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  colPro:           { borderColor: "#00B5A520" },
  colHead:          { fontSize: 12, fontWeight: "800", color: "#94a3b8", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 },
  featureRow:       { flexDirection: "row", alignItems: "flex-start", gap: 6, marginBottom: 8 },
  checkFree:        { color: "#334155", fontSize: 12, marginTop: 1 },
  checkPro:         { color: "#00B5A5", fontSize: 12, marginTop: 1 },
  featureText:      { fontSize: 11, color: "#475569", flex: 1, lineHeight: 16 },
  featureTextPro:   { color: "#94a3b8" },

  footer:           { flexDirection: "row", justifyContent: "center", alignItems: "center", flexWrap: "wrap", marginBottom: 20 },
  footerLink:       { color: "#4a7fa5", fontSize: 11 },
  footerDot:        { color: "#334155", fontSize: 11 },

  highlights:       { gap: 10, marginBottom: 28 },
  hlCard:           { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, borderWidth: 1, borderColor: "#1e3a5f", flexDirection: "row", alignItems: "flex-start", gap: 12 },
  hlIcon:           { fontSize: 22, marginTop: 1 },
  hlBody:           { flex: 1 },
  hlTitle:          { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 3 },
  hlDesc:           { fontSize: 11, color: "#64748b", lineHeight: 16 },

  closeBtn:         { alignItems: "center", paddingVertical: 10 },
  closeBtnText:     { color: "#334155", fontSize: 13 },
});

function HighlightCard({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <View style={s.hlCard}>
      <Text style={s.hlIcon}>{icon}</Text>
      <View style={s.hlBody}>
        <Text style={s.hlTitle}>{title}</Text>
        <Text style={s.hlDesc}>{desc}</Text>
      </View>
    </View>
  );
}
