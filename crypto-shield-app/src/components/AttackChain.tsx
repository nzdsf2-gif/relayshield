import React from "react";
import { View, Text, StyleSheet } from "react-native";

interface Props {
  dims: Record<string, number>;
  score: number;
}

const STAGES = [
  { key: "breach",      label: "Data\nBreach",      icon: "💾", tip: "Credentials in breach database",         dimKey: "breach_exposure" },
  { key: "infostealer", label: "Infostealer\nHit",  icon: "🕵", tip: "Active credential harvesting detected",  dimKey: "infostealer_density" },
  { key: "session",     label: "Session\nStolen",    icon: "🍪", tip: "Live session cookie in criminal archive", dimKey: "session_exposure" },
  { key: "takeover",   label: "Account\nTakeover",  icon: "🔓", tip: "Risk threshold for ATO reached",         dimKey: null },
];

function stageColor(index: number, active: boolean): string {
  if (!active) return "#1e3a5f";
  if (index >= 3) return "#ef4444";
  if (index >= 2) return "#f97316";
  if (index >= 1) return "#facc15";
  return "#22c55e";
}

export function AttackChain({ dims, score }: Props) {
  const active = [
    (dims.breach_exposure ?? 0) > 0,
    (dims.infostealer_density ?? 0) > 0,
    (dims.session_exposure ?? 0) > 0,
    score >= 45,
  ];

  // Find the furthest active stage
  let currentStage = -1;
  active.forEach((a, i) => { if (a) currentStage = i; });

  const warningMsg =
    currentStage >= 2 ? "⚠ Active session exposure — attacker can bypass 2FA without a password"
    : currentStage >= 1 ? "Active credential harvesting on this domain. Session theft is the next step in the attack chain."
    : currentStage >= 0 ? "Breach data is the raw material for infostealer targeting. Monitor for escalation."
    : "No active attack chain signals detected.";

  const warningColor =
    currentStage >= 2 ? "#ef4444"
    : currentStage >= 1 ? "#f97316"
    : currentStage >= 0 ? "#facc15"
    : "#22c55e";

  return (
    <View style={styles.card}>
      <Text style={styles.title}>ATTACK CHAIN POSITION</Text>
      <Text style={styles.subtitle}>Where this domain sits in the identity attack sequence</Text>

      {/* Timeline */}
      <View style={styles.track}>
        {STAGES.map((stage, i) => {
          const isActive  = active[i];
          const isCurrent = i === currentStage;
          const color     = stageColor(i, isActive);
          const isLast    = i === STAGES.length - 1;

          return (
            <View key={stage.key} style={styles.stageWrap}>
              {/* Connector line before this stage */}
              {i > 0 && (
                <View style={[styles.connector, { backgroundColor: active[i - 1] && isActive ? stageColor(i - 1, true) : "#1e3a5f" }]} />
              )}

              <View style={styles.stageCol}>
                <View style={[styles.dot, { borderColor: color, shadowColor: color }]}>
                  <Text style={[styles.dotIcon, { opacity: isActive ? 1 : 0.3 }]}>
                    {isActive ? stage.icon : "·"}
                  </Text>
                </View>
                <Text style={[styles.stageLabel, { color: isActive ? "#e2e8f0" : "#334155" }]}>
                  {stage.label}
                </Text>
                {isCurrent && (
                  <Text style={[styles.youAreHere, { color }]}>← YOU ARE HERE</Text>
                )}
              </View>
            </View>
          );
        })}
      </View>

      {/* Warning message */}
      <Text style={[styles.warning, { color: warningColor }]}>{warningMsg}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card:         { backgroundColor: "#060b18", borderRadius: 10, padding: 14, marginTop: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  title:        { fontSize: 10, fontWeight: "700", color: "#4a7fa5", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 2 },
  subtitle:     { fontSize: 11, color: "#334155", marginBottom: 16 },

  track:        { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12, position: "relative" },
  stageWrap:    { flex: 1, alignItems: "center", flexDirection: "row" },
  connector:    { flex: 1, height: 2, marginTop: -20, marginHorizontal: -2 },
  stageCol:     { alignItems: "center", flex: 1 },

  dot:          {
    width: 32, height: 32, borderRadius: 16, borderWidth: 2,
    backgroundColor: "#060b18", alignItems: "center", justifyContent: "center",
    shadowOpacity: 0.4, shadowRadius: 6, shadowOffset: { width: 0, height: 0 }, elevation: 4,
  },
  dotIcon:      { fontSize: 14 },
  stageLabel:   { fontSize: 9, textAlign: "center", marginTop: 6, lineHeight: 13 },
  youAreHere:   { fontSize: 8, fontWeight: "800", letterSpacing: 0.3, marginTop: 3, textAlign: "center" },
  warning:      { fontSize: 12, lineHeight: 18, fontWeight: "500" },
});
