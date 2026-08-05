import React, { useState } from "react";
import { Modal, View, Text, TouchableOpacity, StyleSheet, Dimensions } from "react-native";

const { width } = Dimensions.get("window");

const STEPS = [
  {
    icon: "💼",
    title: "Wallets",
    body: "Add your EVM, Solana, TON, or Bitcoin wallets here. Crypto Shield scans them continuously for threats and scores your risk.",
    tab: "Wallets tab (bottom bar)",
  },
  {
    icon: "🔍",
    title: "Scan",
    body: "Spot-check any wallet address, EVM token, SOL token, NFT collection, or Bitcoin address before interacting with it.",
    tab: "Scan tab (bottom bar)",
  },
  {
    icon: "🛡",
    title: "Security Sweep",
    body: "Run a full sweep from the Wallets screen — checks for address poisoning lookalikes, breach exposure, and infostealer logs.",
    tab: "Wallets → Security Sweep button",
  },
  {
    icon: "📊",
    title: "Intel Feed",
    body: "Live threat intelligence from 82+ monitored Telegram criminal marketplaces. Tap any indicator to investigate.",
    tab: "Intel tab (bottom bar)",
  },
];

interface Props {
  visible: boolean;
  onDone: () => void;
}

export function TourOverlay({ visible, onDone }: Props) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  function next() {
    if (isLast) { onDone(); }
    else { setStep(s => s + 1); }
  }

  function skip() { onDone(); }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      statusBarTranslucent
    >
      <View style={s.backdrop}>
        <View style={s.card}>
          {/* Progress dots */}
          <View style={s.dots}>
            {STEPS.map((_, i) => (
              <View key={i} style={[s.dot, i === step && s.dotActive]} />
            ))}
          </View>

          <Text style={s.icon}>{current.icon}</Text>
          <Text style={s.title}>{current.title}</Text>
          <Text style={s.body}>{current.body}</Text>
          <View style={s.tabHint}>
            <Text style={s.tabHintText}>📍 {current.tab}</Text>
          </View>

          <View style={s.row}>
            <TouchableOpacity style={s.skipBtn} onPress={skip}>
              <Text style={s.skipText}>Skip tour</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.nextBtn} onPress={next}>
              <Text style={s.nextText}>{isLast ? "Get started →" : "Next →"}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(10,22,40,0.88)",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  card: {
    width: width - 48,
    backgroundColor: "#0F1F3D",
    borderRadius: 20,
    padding: 28,
    borderWidth: 1,
    borderColor: "#1e3a5f",
    alignItems: "center",
  },
  dots: { flexDirection: "row", gap: 6, marginBottom: 24 },
  dot:  { width: 6, height: 6, borderRadius: 3, backgroundColor: "#1e3a5f" },
  dotActive: { backgroundColor: "#00B5A5", width: 18 },

  icon:  { fontSize: 48, marginBottom: 14 },
  title: { fontSize: 22, fontWeight: "800", color: "#f1f5f9", marginBottom: 12, textAlign: "center" },
  body:  { fontSize: 14, color: "#94a3b8", lineHeight: 22, textAlign: "center", marginBottom: 16 },

  tabHint: { backgroundColor: "#0a1628", borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, marginBottom: 24 },
  tabHintText: { fontSize: 11, color: "#00B5A5", fontWeight: "600" },

  row:     { flexDirection: "row", gap: 12, alignItems: "center" },
  skipBtn: { paddingVertical: 10, paddingHorizontal: 16 },
  skipText:{ fontSize: 13, color: "#334155" },
  nextBtn: { backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 11, paddingHorizontal: 24 },
  nextText:{ fontSize: 14, fontWeight: "800", color: "#0a1628" },
});
