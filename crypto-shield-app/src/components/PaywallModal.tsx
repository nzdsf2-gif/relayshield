import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, Modal, Linking } from "react-native";

interface Props {
  visible: boolean;
  onClose: () => void;
  feature: string;       // e.g. "Threat Intel Feed"
  requiredPlan: "personal" | "ti";
}

const PRICING_URL = "https://pricing.relayshield.net";

const PLAN_DETAILS = {
  personal: {
    name: "Personal Plan",
    price: "$10.99/mo",
    priceSub: "7 days free, then cancel any time",
    trialNote: "Try free for 7 days — cancel any time before you're charged.",
    color: "#00B5A5",
    features: [
      "Unlimited token + domain scans",
      "Breach & infostealer monitoring",
      "Address poisoning sweep",
      "Real-time wallet risk scoring",
      "SIM swap monitoring",
    ],
  },
  ti: {
    name: "TI Subscription",
    price: "$49.99/mo",
    priceSub: "Cancel any time · No trial",
    trialNote: "No free trial — subscribe when you're ready.",
    color: "#7c3aed",
    features: [
      "Everything in Personal",
      "Live dark channel IOC feed",
      "Threat of the Week briefings",
      "CISA KEV vulnerability alerts",
      "Actor profile intelligence",
      "STIX/TAXII 2.1 export",
    ],
  },
};

export function PaywallModal({ visible, onClose, feature, requiredPlan }: Props) {
  const plan = PLAN_DETAILS[requiredPlan];
  return (
    <Modal visible={visible} transparent animationType="slide">
      <View style={s.overlay}>
        <View style={s.sheet}>
          <TouchableOpacity style={s.closeBtn} onPress={onClose}>
            <Text style={s.closeBtnText}>✕</Text>
          </TouchableOpacity>

          <View style={[s.badge, { backgroundColor: plan.color + "20", borderColor: plan.color + "40" }]}>
            <Text style={[s.badgeText, { color: plan.color }]}>🔒 {plan.name} Required</Text>
          </View>

          <Text style={s.title}>{feature}</Text>
          <Text style={s.sub}>This feature requires the {plan.name}. {plan.trialNote}</Text>

          <View style={s.featureList}>
            {plan.features.map((f, i) => (
              <View key={i} style={s.featureRow}>
                <Text style={[s.featureCheck, { color: plan.color }]}>✓</Text>
                <Text style={s.featureText}>{f}</Text>
              </View>
            ))}
          </View>

          <View style={s.priceRow}>
            <Text style={[s.price, { color: plan.color }]}>{plan.price}</Text>
            <Text style={s.priceSub}>{plan.priceSub}</Text>
          </View>

          <TouchableOpacity
            style={[s.upgradeBtn, { backgroundColor: plan.color }]}
            onPress={() => { Linking.openURL(PRICING_URL); onClose(); }}
          >
            <Text style={s.upgradeBtnText}>Subscribe at relayshield.net →</Text>
          </TouchableOpacity>

          <Text style={s.note}>
            After subscribing, this feature unlocks automatically — no need to do anything else in the app.
          </Text>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay:      { flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  sheet:        { backgroundColor: "#0F1F3D", borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 28, paddingBottom: 40 },
  closeBtn:     { position: "absolute", top: 16, right: 20, zIndex: 1 },
  closeBtnText: { fontSize: 18, color: "#64748b" },
  badge:        { alignSelf: "flex-start", borderRadius: 10, paddingHorizontal: 12, paddingVertical: 5, borderWidth: 1, marginBottom: 14 },
  badgeText:    { fontSize: 11, fontWeight: "800" },
  title:        { fontSize: 20, fontWeight: "800", color: "#fff", marginBottom: 8 },
  sub:          { fontSize: 13, color: "#64748b", lineHeight: 20, marginBottom: 18 },
  featureList:  { backgroundColor: "#060b18", borderRadius: 10, padding: 14, marginBottom: 18 },
  featureRow:   { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 8 },
  featureCheck: { fontSize: 13, fontWeight: "700", marginTop: 1 },
  featureText:  { fontSize: 13, color: "#94a3b8", flex: 1, lineHeight: 18 },
  priceRow:     { flexDirection: "row", alignItems: "baseline", gap: 10, marginBottom: 16 },
  price:        { fontSize: 26, fontWeight: "900" },
  priceSub:     { fontSize: 12, color: "#64748b" },
  upgradeBtn:   { borderRadius: 12, paddingVertical: 15, alignItems: "center", marginBottom: 14 },
  upgradeBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },
  note:         { fontSize: 11, color: "#334155", textAlign: "center", lineHeight: 16 },
});
