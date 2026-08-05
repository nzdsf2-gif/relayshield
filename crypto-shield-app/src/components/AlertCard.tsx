import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Linking } from "react-native";
import { SimLockGuide } from "./SimLockGuide";

export interface Alert {
  id: string;
  type: "BREACH" | "INFOSTEALER" | "SIM_SWAP" | "NHI" | "SUPPLY_CHAIN" | "TOKEN_RISK";
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  title: string;
  detail: string;
  wallet?: string;
  walletLabel?: string;
  timestamp: string;
  acknowledged: boolean;
  isDemo?: boolean;
}

interface Props {
  alert: Alert;
  onAcknowledge: (id: string) => void;
  onDetail: (alert: Alert) => void;
}

const TYPE_ICONS: Record<Alert["type"], string> = {
  BREACH:       "💾",
  INFOSTEALER:  "🕵",
  SIM_SWAP:     "📱",
  NHI:          "🔑",
  SUPPLY_CHAIN: "🔗",
  TOKEN_RISK:   "⚠️",
};

// Remediation links keyed by alert type
const REMEDIATION: Record<Alert["type"], { label: string; url: string } | null> = {
  BREACH:       { label: "Change passwords", url: "https://haveibeenpwned.com" },
  INFOSTEALER:  { label: "Revoke active sessions", url: "https://myaccount.google.com/security" },
  SIM_SWAP:     { label: "Lock SIM with carrier", url: "https://relayshield.net" },
  NHI:          { label: "Rotate API keys", url: "https://api.relayshield.net/developers" },
  SUPPLY_CHAIN: { label: "Check vendor status", url: "https://relayshield.net" },
  TOKEN_RISK:   { label: "Swap out via Jupiter", url: "https://jup.ag" },
};

function severityColor(s: Alert["severity"]) {
  return s === "CRITICAL" ? "#ef4444" : s === "HIGH" ? "#f97316" : s === "MEDIUM" ? "#facc15" : "#22c55e";
}

export function AlertCard({ alert, onAcknowledge, onDetail }: Props) {
  const color = severityColor(alert.severity);
  const ago   = formatAgo(alert.timestamp);
  const remed = REMEDIATION[alert.type];
  const [showSimGuide, setShowSimGuide] = useState(false);

  return (
    <TouchableOpacity
      style={[styles.card, { borderLeftColor: color, opacity: alert.acknowledged ? 0.6 : 1 }]}
      onPress={() => onDetail(alert)}
      activeOpacity={0.8}
    >
      <View style={styles.header}>
        <View style={styles.left}>
          <Text style={styles.icon}>{TYPE_ICONS[alert.type]}</Text>
          <View style={[styles.badge, { backgroundColor: color + "20", borderColor: color + "40" }]}>
            <Text style={[styles.badgeText, { color }]}>{alert.severity}</Text>
          </View>
          {alert.isDemo && (
            <View style={styles.demoPill}>
              <Text style={styles.demoPillText}>SAMPLE</Text>
            </View>
          )}
        </View>
        <Text style={styles.ago}>{ago}</Text>
      </View>

      <Text style={styles.title}>{alert.title}</Text>
      <Text style={styles.detail} numberOfLines={2}>{alert.detail}</Text>

      {alert.wallet && (
        <Text style={styles.wallet} numberOfLines={1}>
          {alert.walletLabel ? `${alert.walletLabel} · ` : ""}{alert.wallet.slice(0, 8)}...{alert.wallet.slice(-6)}
        </Text>
      )}

      {showSimGuide && <SimLockGuide visible={showSimGuide} onClose={() => setShowSimGuide(false)} />}

      <View style={styles.actionRow}>
        {remed && !alert.acknowledged && (
          <TouchableOpacity
            style={[styles.remedBtn, { borderColor: color + "50", backgroundColor: color + "12" }]}
            onPress={() => alert.type === "SIM_SWAP" ? setShowSimGuide(true) : Linking.openURL(remed.url)}
          >
            <Text style={[styles.remedText, { color }]}>→ {remed.label}</Text>
          </TouchableOpacity>
        )}
        {!alert.acknowledged && (
          <TouchableOpacity
            style={[styles.ackBtn, { borderColor: color + "40" }]}
            onPress={() => onAcknowledge(alert.id)}
          >
            <Text style={[styles.ackText, { color }]}>✓ Ack</Text>
          </TouchableOpacity>
        )}
      </View>
    </TouchableOpacity>
  );
}

function formatAgo(ts: string) {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const styles = StyleSheet.create({
  card:      { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 10, borderLeftWidth: 3 },
  header:    { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  left:      { flexDirection: "row", alignItems: "center", gap: 8 },
  icon:      { fontSize: 16 },
  badge:     { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10, borderWidth: 1 },
  badgeText: { fontSize: 10, fontWeight: "700" },
  ago:       { fontSize: 11, color: "#64748b" },
  title:     { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 4 },
  detail:    { fontSize: 12, color: "#94a3b8", lineHeight: 18 },
  wallet:    { fontSize: 11, color: "#4a7fa5", fontFamily: "monospace", marginTop: 6 },
  actionRow: { flexDirection: "row", gap: 8, marginTop: 10, alignItems: "center" },
  remedBtn:  { flex: 1, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 6, borderWidth: 1 },
  remedText: { fontSize: 12, fontWeight: "700" },
  ackBtn:      { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 6, borderWidth: 1, borderColor: "#1e3a5f" },
  ackText:     { fontSize: 12, fontWeight: "600", color: "#64748b" },
  demoPill:    { backgroundColor: "#f59e0b20", borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1, borderWidth: 1, borderColor: "#f59e0b40" },
  demoPillText:{ fontSize: 9, fontWeight: "800", color: "#f59e0b" },
});
