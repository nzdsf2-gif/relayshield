import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, Share } from "react-native";
import { ACHIEVEMENTS } from "../hooks/useGameification";

interface Props {
  streak: number;
  shieldScore: number;
  referralCode: string;
}

function gradeFromScore(score: number) {
  if (score >= 800) return { icon: "🛡", color: "#00B5A5", label: "Elite Defender" };
  if (score >= 500) return { icon: "🛡", color: "#22c55e", label: "Guardian" };
  if (score >= 200) return { icon: "🛡", color: "#facc15", label: "Protector" };
  if (score >= 50)  return { icon: "🛡", color: "#f97316", label: "Watcher" };
  return                   { icon: "🛡", color: "#4a7fa5", label: "Getting Started" };
}

export function StreakCard({ streak, shieldScore, referralCode }: Props) {
  const { icon, color, label } = gradeFromScore(shieldScore);

  async function shareReferral() {
    await Share.share({
      message: `I use CryptoShield by RelayShield to protect my wallets. Join me — use my referral code ${referralCode} at relayshield.net/app for a free month. t.me/RelayShield`,
      title: "CryptoShield — Wallet Security",
    });
  }

  return (
    <View style={styles.card}>
      <View style={styles.row}>

        {/* Streak */}
        <View style={styles.statBox}>
          <Text style={styles.statBig}>{streak}</Text>
          <Text style={styles.statLabel}>🔥 Day Streak</Text>
          <Text style={styles.statSub}>
            {streak === 0 ? "Run a scan to start your streak" : streak >= 7 ? "On fire! Keep scanning daily" : `${7 - streak} days to 7-day streak — scan today`}
          </Text>
        </View>

        {/* Shield grade */}
        <View style={styles.statBox}>
          <Text style={[styles.shieldIcon, { color }]}>{icon}</Text>
          <Text style={[styles.statLabel, { color }]}>{label}</Text>
          <Text style={styles.statSub}>{shieldScore} pts</Text>
        </View>

      </View>

      {/* Referral */}
      <TouchableOpacity style={styles.referralRow} onPress={shareReferral}>
        <View>
          <Text style={styles.referralLabel}>🤝 Refer a friend</Text>
          <Text style={styles.referralCode}>{referralCode}</Text>
        </View>
        <Text style={styles.referralShare}>Share →</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card:          { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  row:           { flexDirection: "row", gap: 12, marginBottom: 12 },
  statBox:       { flex: 1, backgroundColor: "#060b18", borderRadius: 10, padding: 12, alignItems: "center" },
  statBig:       { fontSize: 28, fontWeight: "800", color: "#f97316" },
  shieldIcon:    { fontSize: 32, marginBottom: 2 },
  statLabel:     { fontSize: 11, color: "#94a3b8", marginTop: 4, fontWeight: "600" },
  statSub:       { fontSize: 10, color: "#e2e8f0", marginTop: 2, textAlign: "center" },
  referralRow:   { flexDirection: "row", justifyContent: "space-between", alignItems: "center", backgroundColor: "#060b18", borderRadius: 8, padding: 10 },
  referralLabel: { fontSize: 11, color: "#4a7fa5", marginBottom: 2 },
  referralCode:  { fontSize: 14, color: "#00B5A5", fontWeight: "800", fontFamily: "monospace" },
  referralShare: { fontSize: 12, color: "#00B5A5", fontWeight: "700" },
});
