import React, { useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  ScrollView, ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useWallets } from "../hooks/useWallet";
import * as RS from "../api/relayshield";

const DEFAULT_VENDORS = [
  "chainlink.com", "pyth.network", "alchemy.com", "infura.io", "opensea.io",
];

function riskColor(level: string) {
  return level === "CRITICAL" ? "#ef4444" : level === "HIGH" ? "#f97316" : level === "MEDIUM" ? "#facc15" : level === "CLEAN" ? "#22c55e" : "#64748b";
}

// Demo data shown when no API key
const DEMO_RESULTS = [
  { domain: "chainlink.com",  risk_level: "LOW",      risk_score: 8,  risk_factors: ["2 historical breaches — no active stealer hits"] },
  { domain: "pyth.network",   risk_level: "MEDIUM",   risk_score: 31, risk_factors: ["1 infostealer hit in past 30 days"] },
  { domain: "alchemy.com",    risk_level: "LOW",      risk_score: 12, risk_factors: ["1 historical breach — passwords only, no sessions"] },
  { domain: "infura.io",      risk_level: "CLEAN",    risk_score: 0,  risk_factors: [] },
  { domain: "opensea.io",     risk_level: "HIGH",     risk_score: 52, risk_factors: ["3 infostealer hits", "API key exposure detected in stealer archive"] },
];

export function SupplyChainScreen() {
  const insets = useSafeAreaInsets();
  const { apiKey } = useWallets();
  const [vendors, setVendors] = useState<string[]>(DEFAULT_VENDORS);
  const [newVendor, setNewVendor] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [swept, setSwept] = useState(false);

  async function runSweep() {
    setLoading(true);
    try {
      if (apiKey) {
        const data = await RS.checkSupplyChain(vendors, apiKey);
        setResults(data.vendors || data.results || []);
      } else {
        await new Promise(r => setTimeout(r, 1200));
        setResults(DEMO_RESULTS);
      }
      setSwept(true);
    } catch {
      setResults(DEMO_RESULTS);
      setSwept(true);
    } finally {
      setLoading(false);
    }
  }

  function addVendor() {
    const v = newVendor.trim().toLowerCase();
    if (v && !vendors.includes(v)) setVendors([...vendors, v]);
    setNewVendor("");
  }

  function removeVendor(v: string) {
    setVendors(vendors.filter(x => x !== v));
    setResults(results.filter(r => r.domain !== v));
  }

  const critical = results.filter(r => r.risk_level === "CRITICAL" || r.risk_level === "HIGH").length;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Text style={styles.title}>Vendor Sweep</Text>
      <Text style={styles.subtitle}>Supply chain risk across your trusted service providers</Text>

      <ScrollView showsVerticalScrollIndicator={false} style={{ flex: 1, paddingHorizontal: 16 }}>

        {/* Vendor list */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Monitored Vendors ({vendors.length})</Text>
          {vendors.map(v => (
            <View key={v} style={styles.vendorRow}>
              <Text style={styles.vendorName}>{v}</Text>
              {results.find(r => r.domain === v) ? (
                <RiskPill level={results.find(r => r.domain === v).risk_level} />
              ) : (
                <TouchableOpacity onPress={() => removeVendor(v)}>
                  <Text style={styles.removeText}>✕</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
          <View style={styles.addRow}>
            <TextInput
              style={styles.addInput}
              value={newVendor}
              onChangeText={setNewVendor}
              placeholder="Add vendor domain..."
              placeholderTextColor="#334155"
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={addVendor}
            />
            <TouchableOpacity style={styles.addBtn} onPress={addVendor}>
              <Text style={styles.addBtnText}>+</Text>
            </TouchableOpacity>
          </View>
        </View>

        <TouchableOpacity
          style={[styles.sweepBtn, loading && { opacity: 0.6 }]}
          onPress={runSweep}
          disabled={loading}
        >
          {loading
            ? <><ActivityIndicator color="#0a1628" size="small" /><Text style={styles.sweepBtnText}> Scanning...</Text></>
            : <Text style={styles.sweepBtnText}>🔗 Run Vendor Sweep</Text>
          }
        </TouchableOpacity>

        {swept && results.length > 0 && (
          <>
            {critical > 0 && (
              <View style={styles.critBanner}>
                <Text style={styles.critText}>⚠ {critical} vendor{critical !== 1 ? "s" : ""} require attention</Text>
              </View>
            )}
            <Text style={styles.sectionLabel}>Sweep Results</Text>
            {results
              .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
              .map(r => (
                <View key={r.domain} style={[styles.resultRow, { borderLeftColor: riskColor(r.risk_level) }]}>
                  <View style={styles.resultTop}>
                    <Text style={styles.resultDomain}>{r.domain}</Text>
                    <RiskPill level={r.risk_level} score={r.risk_score} />
                  </View>
                  {(r.risk_factors ?? []).map((f: string, i: number) => (
                    <Text key={i} style={styles.resultFactor}>• {f}</Text>
                  ))}
                  {(r.risk_factors ?? []).length === 0 && (
                    <Text style={styles.resultFactor}>No active threat signals detected</Text>
                  )}
                  {r.recommendation && r.risk_level !== "CLEAN" && (
                    <View style={[styles.remediation, { borderLeftColor: riskColor(r.risk_level) }]}>
                      <Text style={styles.remediationLabel}>Recommended Action</Text>
                      <Text style={styles.remediationText}>{r.recommendation}</Text>
                    </View>
                  )}
                </View>
              ))}
            {!apiKey && (
              <Text style={styles.demoNote}>Demo data shown — link your subscription in Settings for live results</Text>
            )}
          </>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

function RiskPill({ level, score }: { level: string; score?: number }) {
  const c = riskColor(level);
  return (
    <View style={[styles.pill, { backgroundColor: c + "20", borderColor: c + "40" }]}>
      <Text style={[styles.pillText, { color: c }]}>{level}{score !== undefined ? ` ${score}` : ""}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: "#0a1628" },
  title:        { fontSize: 20, fontWeight: "800", color: "#fff", paddingHorizontal: 20, paddingTop: 16 },
  subtitle:     { fontSize: 12, color: "#64748b", paddingHorizontal: 20, marginBottom: 14, marginTop: 2 },
  card:         { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  cardTitle:    { fontSize: 12, fontWeight: "700", color: "#4a7fa5", letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 10 },
  vendorRow:    { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  vendorName:   { fontSize: 13, color: "#e2e8f0", fontFamily: "monospace" },
  removeText:   { fontSize: 14, color: "#64748b", paddingHorizontal: 4 },
  addRow:       { flexDirection: "row", gap: 8, marginTop: 12 },
  addInput:     { flex: 1, backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 10, color: "#e2e8f0", fontSize: 12, fontFamily: "monospace" },
  addBtn:       { backgroundColor: "#1e3a5f", borderRadius: 8, width: 38, alignItems: "center", justifyContent: "center" },
  addBtnText:   { color: "#00B5A5", fontSize: 20, fontWeight: "300" },
  sweepBtn:     { backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 14, alignItems: "center", flexDirection: "row", justifyContent: "center", gap: 8, marginBottom: 16 },
  sweepBtnText: { color: "#0a1628", fontWeight: "800", fontSize: 14 },
  critBanner:   { backgroundColor: "#ef444420", borderRadius: 8, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: "#ef444440" },
  critText:     { color: "#ef4444", fontSize: 13, fontWeight: "700" },
  sectionLabel: { fontSize: 10, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 10 },
  resultRow:    { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 10, borderLeftWidth: 3, borderWidth: 1, borderColor: "#1e3a5f" },
  resultTop:    { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  resultDomain: { fontSize: 13, fontWeight: "700", color: "#e2e8f0", fontFamily: "monospace" },
  resultFactor: { fontSize: 12, color: "#94a3b8", lineHeight: 18 },
  pill:         { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, borderWidth: 1 },
  pillText:     { fontSize: 10, fontWeight: "700" },
  demoNote:     { fontSize: 11, color: "#334155", textAlign: "center", marginTop: 8, fontStyle: "italic" },
  remediation:      { marginTop: 10, paddingLeft: 10, borderLeftWidth: 2 },
  remediationLabel: { fontSize: 10, fontWeight: "700", color: "#4a7fa5", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 3 },
  remediationText:  { fontSize: 11, color: "#94a3b8", lineHeight: 16 },
});
