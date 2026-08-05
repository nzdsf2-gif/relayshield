import React, { useState, useEffect } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useWallets } from "../hooks/useWallet";
import * as RS from "../api/relayshield";
import * as SecureStore from "expo-secure-store";

const HOURS_OPTIONS = [24, 48, 72];

const DEMO_INTEL = [
  { indicator: "185.220.101.47",         type: "C2",          threat_name: "RedLine Stealer C2",        severity: "CRITICAL", source: "Abuse.ch",        first_seen: new Date(Date.now()-3600000).toISOString() },
  { indicator: "login-coinbase-secure.com", type: "PHISHING", threat_name: "Coinbase phishing domain",  severity: "CRITICAL", source: "OpenPhish",       first_seen: new Date(Date.now()-7200000).toISOString() },
  { indicator: "94.131.123.201",          type: "MALWARE",     threat_name: "Vidar Stealer",             severity: "HIGH",     source: "Emerging Threats",first_seen: new Date(Date.now()-10800000).toISOString() },
  { indicator: "metamask-wallet-app.io",  type: "PHISHING",    threat_name: "MetaMask phishing",         severity: "CRITICAL", source: "CISA KEV",        first_seen: new Date(Date.now()-14400000).toISOString() },
  { indicator: "45.142.212.100",          type: "C2",          threat_name: "Raccoon Stealer C2",        severity: "HIGH",     source: "Abuse.ch",        first_seen: new Date(Date.now()-18000000).toISOString() },
  { indicator: "verify-ledger-wallet.com",type: "PHISHING",    threat_name: "Ledger phishing domain",    severity: "HIGH",     source: "OpenPhish",       first_seen: new Date(Date.now()-21600000).toISOString() },
  { indicator: "update-trezor-now.net",   type: "PHISHING",    threat_name: "Trezor phishing domain",    severity: "HIGH",     source: "OpenPhish",       first_seen: new Date(Date.now()-25200000).toISOString() },
  { indicator: "103.224.182.251",         type: "RANSOMWARE",  threat_name: "LockBit callback",          severity: "CRITICAL", source: "CISA KEV",        first_seen: new Date(Date.now()-28800000).toISOString() },
];

const TYPE_COLORS: Record<string, string> = {
  C2: "#ef4444", PHISHING: "#f97316", MALWARE: "#facc15",
  RANSOMWARE: "#ef4444", TROJAN: "#f97316", BOTNET: "#f97316",
};

function severityColor(s: string) {
  return s === "CRITICAL" ? "#ef4444" : s === "HIGH" ? "#f97316" : s === "MEDIUM" ? "#facc15" : "#22c55e";
}

function formatAgo(ts: string) {
  const m = Math.floor((Date.now() - new Date(ts).getTime()) / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function IntelScreen() {
  const insets = useSafeAreaInsets();
  const { apiKey } = useWallets();
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [indicators, setIndicators] = useState<any[]>([]);
  const [filter, setFilter] = useState<string | null>(null);
  const [source, setSource] = useState<"rs" | "public" | "demo">("demo");

  useEffect(() => { load(); }, [hours]);

  async function fetchPublicFeeds(): Promise<any[]> {
    const results: any[] = [];
    try {
      // Abuse.ch ThreatFox — free, no key
      const tfResp = await fetch("https://threatfox-api.abuse.ch/api/v1/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: "get_iocs", days: hours <= 24 ? 1 : hours <= 48 ? 2 : 3 }),
      });
      const tfData = await tfResp.json();
      const tfIocs: any[] = tfData.data ?? [];
      tfIocs.slice(0, 30).forEach(ioc => {
        results.push({
          indicator:   ioc.ioc ?? ioc.ioc_value ?? "",
          type:        (ioc.threat_type ?? "MALWARE").toUpperCase().replace(/ /g, "_"),
          threat_name: ioc.malware ?? ioc.threat_type ?? "Unknown",
          severity:    ioc.confidence_level >= 90 ? "CRITICAL" : ioc.confidence_level >= 70 ? "HIGH" : "MEDIUM",
          source:      "Abuse.ch ThreatFox",
          first_seen:  ioc.first_seen ?? new Date().toISOString(),
        });
      });
    } catch {}
    try {
      // URLhaus — recent malicious URLs
      const uhResp = await fetch("https://urlhaus-api.abuse.ch/v1/urls/recent/limit/20/", { method: "POST" });
      const uhData = await uhResp.json();
      const uhUrls: any[] = uhData.urls ?? [];
      uhUrls.forEach(u => {
        if (u.url_status === "online") {
          results.push({
            indicator:   u.url ?? "",
            type:        "MALWARE",
            threat_name: u.threat ?? "Malicious URL",
            severity:    "HIGH",
            source:      "Abuse.ch URLhaus",
            first_seen:  u.date_added ?? new Date().toISOString(),
          });
        }
      });
    } catch {}
    return results.sort((a, b) => new Date(b.first_seen).getTime() - new Date(a.first_seen).getTime());
  }

  async function load(isRefresh = false) {
    isRefresh ? setRefreshing(true) : setLoading(true);
    try {
      if (apiKey) {
        // Try RS intel feed first — works with any valid RS key
        try {
          const data = await RS.getTrendingThreats(hours, apiKey);
          const trending: Record<string, any[]> = data.trending ?? {};
          const flat = Object.entries(trending).flatMap(([type, iocs]) =>
            (iocs as any[]).map(ioc => ({
              indicator:   ioc.ioc_value,
              type,
              threat_name: ioc.malware || type,
              severity:    ioc.confidence >= 0.9 ? "CRITICAL" : ioc.confidence >= 0.7 ? "HIGH" : "MEDIUM",
              source:      ioc.source || ioc.channel || "RelayShield",
              first_seen:  ioc.seen_ts,
            }))
          ).sort((a, b) => new Date(b.first_seen).getTime() - new Date(a.first_seen).getTime());
          if (flat.length > 0) { setIndicators(flat); setSource("rs"); return; }
        } catch {}
      }
      // No key or RS returned empty → public feeds (no account needed)
      const pub = await fetchPublicFeeds();
      if (pub.length > 0) { setIndicators(pub); setSource("public"); return; }
      // Ultimate fallback
      setIndicators(DEMO_INTEL);
      setSource("demo");
    } catch {
      setIndicators(DEMO_INTEL);
      setSource("demo");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }

  const types = [...new Set(indicators.map(i => i.type))];
  const filtered = filter ? indicators.filter(i => i.type === filter) : indicators;
  const critCount = indicators.filter(i => i.severity === "CRITICAL").length;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Threat Intel</Text>
          <Text style={styles.subtitle}>
            {source === "rs" ? "RelayShield feed" : source === "public" ? "Public feeds (Abuse.ch)" : "Sample data"} · {indicators.length} indicators
          </Text>
        </View>
        {critCount > 0 && (
          <View style={styles.critBadge}>
            <Text style={styles.critBadgeText}>{critCount} CRITICAL</Text>
          </View>
        )}
      </View>

      <>
          {/* Hours selector */}
          <View style={styles.hoursRow}>
            {HOURS_OPTIONS.map(h => (
              <TouchableOpacity
                key={h}
                style={[styles.hoursBtn, hours === h && styles.hoursBtnActive]}
                onPress={() => setHours(h)}
              >
                <Text style={[styles.hoursBtnText, hours === h && { color: "#00B5A5" }]}>Last {h}h</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Type filter pills */}
          {types.length > 0 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filterRow} contentContainerStyle={{ gap: 6, paddingHorizontal: 16 }}>
              <TouchableOpacity
                style={[styles.filterPill, !filter && styles.filterPillActive]}
                onPress={() => setFilter(null)}
              >
                <Text style={[styles.filterPillText, !filter && { color: "#00B5A5" }]}>All</Text>
              </TouchableOpacity>
              {types.map(t => (
                <TouchableOpacity
                  key={t}
                  style={[styles.filterPill, filter === t && styles.filterPillActive]}
                  onPress={() => setFilter(filter === t ? null : t)}
                >
                  <Text style={[styles.filterPillText, { color: TYPE_COLORS[t] || "#94a3b8" }, filter === t && styles.filterPillTextActive]}>
                    {t}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          {loading ? (
            <View style={styles.loadingWrap}>
              <ActivityIndicator color="#00B5A5" size="large" />
              <Text style={styles.loadingText}>Querying live corpus...</Text>
            </View>
          ) : (
            <ScrollView
              showsVerticalScrollIndicator={false}
              style={{ flex: 1, paddingHorizontal: 16 }}
              refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#00B5A5" />}
            >
              {filtered.map((ioc, i) => (
                <View key={i} style={[styles.iocCard, { borderLeftColor: severityColor(ioc.severity) }]}>
                  <View style={styles.iocTop}>
                    <View style={[styles.typeBadge, { backgroundColor: (TYPE_COLORS[ioc.type] || "#64748b") + "20" }]}>
                      <Text style={[styles.typeBadgeText, { color: TYPE_COLORS[ioc.type] || "#64748b" }]}>{ioc.type}</Text>
                    </View>
                    <View style={[styles.sevBadge, { backgroundColor: severityColor(ioc.severity) + "20" }]}>
                      <Text style={[styles.sevBadgeText, { color: severityColor(ioc.severity) }]}>{ioc.severity}</Text>
                    </View>
                    <Text style={styles.iocAgo}>{formatAgo(ioc.first_seen)}</Text>
                  </View>
                  <Text style={styles.iocIndicator} numberOfLines={1}>{ioc.indicator}</Text>
                  <Text style={styles.iocName}>{ioc.threat_name}</Text>
                  <Text style={styles.iocSource}>Source: {ioc.source}</Text>
                </View>
              ))}
              {source === "demo" && (
                <Text style={styles.demoNote}>Sample data — connect to live feeds via Settings</Text>
              )}
              {source === "public" && (
                <Text style={styles.demoNote}>Live public feeds · Link your subscription in Settings for RelayShield intelligence</Text>
              )}
              <View style={{ height: 40 }} />
            </ScrollView>
          )}
        </>
    </View>
  );
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: "#0a1628" },
  header:          { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", paddingHorizontal: 20, paddingTop: 16, marginBottom: 12 },
  title:           { fontSize: 20, fontWeight: "800", color: "#fff" },
  subtitle:        { fontSize: 12, color: "#64748b", marginTop: 2 },
  critBadge:       { backgroundColor: "#ef444420", borderRadius: 10, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: "#ef444440" },
  critBadgeText:   { fontSize: 10, color: "#ef4444", fontWeight: "700" },
  hoursRow:        { flexDirection: "row", paddingHorizontal: 16, gap: 8, marginBottom: 10 },
  hoursBtn:        { flex: 1, backgroundColor: "#0F1F3D", borderRadius: 8, paddingVertical: 8, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  hoursBtnActive:  { borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  hoursBtnText:    { fontSize: 12, color: "#64748b", fontWeight: "600" },
  filterRow:       { marginBottom: 12, maxHeight: 38 },
  filterPill:      { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: "#0F1F3D", borderWidth: 1, borderColor: "#1e3a5f" },
  filterPillActive:{ borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  filterPillText:  { fontSize: 11, color: "#64748b", fontWeight: "600" },
  filterPillTextActive: { color: "#00B5A5" },
  loadingWrap:     { flex: 1, alignItems: "center", justifyContent: "center", gap: 14 },
  loadingText:     { fontSize: 13, color: "#4a7fa5" },
  iocCard:         { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 8, borderLeftWidth: 3, borderWidth: 1, borderColor: "#1e3a5f" },
  iocTop:          { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 },
  typeBadge:       { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6 },
  typeBadgeText:   { fontSize: 9, fontWeight: "800", letterSpacing: 0.3 },
  sevBadge:        { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6 },
  sevBadgeText:    { fontSize: 9, fontWeight: "800", letterSpacing: 0.3 },
  iocAgo:          { fontSize: 10, color: "#64748b", marginLeft: "auto" },
  iocIndicator:    { fontSize: 12, color: "#e2e8f0", fontFamily: "monospace", marginBottom: 4 },
  iocName:         { fontSize: 12, color: "#94a3b8", marginBottom: 3 },
  iocSource:       { fontSize: 10, color: "#4a7fa5" },
  demoNote:        { fontSize: 11, color: "#334155", textAlign: "center", marginTop: 8, fontStyle: "italic" },
});
