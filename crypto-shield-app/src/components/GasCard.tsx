import React, { useState, useEffect } from "react";
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from "react-native";
import { fetchGasPrice, GasPrice } from "../api/alchemy";

interface Props {
  apiKey: string | null;
  gasAlertThreshold: number;  // gwei — alert user when standard falls below this
  onSetThreshold: () => void;
}

const LEVEL_COLOR: Record<GasPrice["level"], string> = {
  LOW:       "#22c55e",
  MEDIUM:    "#facc15",
  HIGH:      "#f97316",
  VERY_HIGH: "#ef4444",
};

const LEVEL_LABEL: Record<GasPrice["level"], string> = {
  LOW:       "🟢 Low — good time to transact",
  MEDIUM:    "🟡 Moderate",
  HIGH:      "🟠 High — consider waiting",
  VERY_HIGH: "🔴 Very high — avoid non-urgent txns",
};

const DEMO_GAS: GasPrice = { slow: 8, standard: 12, fast: 18, baseFee: 10, level: "LOW" };

export function GasCard({ apiKey, gasAlertThreshold, onSetThreshold }: Props) {
  const [gas, setGas]       = useState<GasPrice | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => { load(); }, [apiKey]);

  async function load() {
    setLoading(true);
    try {
      if (apiKey) {
        const data = await fetchGasPrice(apiKey);
        setGas(data);
      } else {
        await new Promise(r => setTimeout(r, 600));
        setGas(DEMO_GAS);
      }
      setLastUpdated(new Date());
    } catch {
      setGas(DEMO_GAS);
    } finally {
      setLoading(false);
    }
  }

  const isAlert = gas && gas.standard <= gasAlertThreshold;
  const color   = gas ? LEVEL_COLOR[gas.level] : "#64748b";

  return (
    <View style={[styles.card, isAlert && styles.cardAlert]}>
      <View style={styles.header}>
        <Text style={styles.title}>⛽ ETH Gas</Text>
        <View style={styles.headerRight}>
          {lastUpdated && (
            <Text style={styles.updated}>
              {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </Text>
          )}
          <TouchableOpacity onPress={load} style={styles.refreshBtn}>
            <Text style={styles.refreshIcon}>{loading ? "…" : "↺"}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading && !gas ? (
        <ActivityIndicator color="#00B5A5" size="small" style={{ marginVertical: 12 }} />
      ) : gas ? (
        <>
          <Text style={[styles.statusLabel, { color }]}>{LEVEL_LABEL[gas.level]}</Text>

          <View style={styles.tierRow}>
            <GasTier label="Slow"     gwei={gas.slow}     color="#64748b" />
            <GasTier label="Standard" gwei={gas.standard} color={color}   bold />
            <GasTier label="Fast"     gwei={gas.fast}     color="#94a3b8" />
            <GasTier label="Base Fee" gwei={gas.baseFee}  color="#4a7fa5" />
          </View>

          {isAlert && (
            <View style={styles.alertBanner}>
              <Text style={styles.alertText}>
                🔔 Gas below your {gasAlertThreshold} gwei alert threshold — good time to transact
              </Text>
            </View>
          )}

          <TouchableOpacity style={styles.thresholdBtn} onPress={onSetThreshold}>
            <Text style={styles.thresholdText}>
              Alert threshold: &lt;{gasAlertThreshold} gwei &nbsp;›
            </Text>
          </TouchableOpacity>
        </>
      ) : null}

      {!apiKey && (
        <Text style={styles.demoNote}>Demo — link your subscription in Settings for live data</Text>
      )}
    </View>
  );
}

function GasTier({ label, gwei, color, bold }: { label: string; gwei: number; color: string; bold?: boolean }) {
  return (
    <View style={styles.tier}>
      <Text style={[styles.tierGwei, { color }, bold && styles.tierGweiBold]}>{gwei}</Text>
      <Text style={styles.tierUnit}>gwei</Text>
      <Text style={styles.tierLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card:          { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  cardAlert:     { borderColor: "#22c55e60" },
  header:        { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  title:         { fontSize: 13, fontWeight: "700", color: "#e2e8f0" },
  headerRight:   { flexDirection: "row", alignItems: "center", gap: 8 },
  updated:       { fontSize: 10, color: "#334155" },
  refreshBtn:    { padding: 4 },
  refreshIcon:   { fontSize: 16, color: "#4a7fa5" },
  statusLabel:   { fontSize: 12, fontWeight: "600", marginBottom: 10 },
  tierRow:       { flexDirection: "row", justifyContent: "space-between" },
  tier:          { alignItems: "center", flex: 1 },
  tierGwei:      { fontSize: 18, fontWeight: "600" },
  tierGweiBold:  { fontSize: 22, fontWeight: "800" },
  tierUnit:      { fontSize: 9, color: "#64748b", marginTop: 1 },
  tierLabel:     { fontSize: 10, color: "#64748b", marginTop: 3 },
  alertBanner:   { backgroundColor: "#22c55e15", borderRadius: 8, padding: 10, marginTop: 10, borderWidth: 1, borderColor: "#22c55e30" },
  alertText:     { fontSize: 12, color: "#22c55e", lineHeight: 18 },
  thresholdBtn:  { marginTop: 10, alignSelf: "flex-end" },
  thresholdText: { fontSize: 11, color: "#4a7fa5" },
  demoNote:      { fontSize: 10, color: "#334155", marginTop: 8, fontStyle: "italic" },
});
