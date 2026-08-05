import React, { useState, useEffect, useCallback } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator,
  Modal, TextInput, Alert, Switch,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import { fetchStablecoinPrices, StablecoinPrice, STABLECOINS } from "../api/alchemy";

const CUSTOM_COINS_KEY = "cs_custom_stablecoins";

const STATUS_COLOR: Record<StablecoinPrice["pegStatus"], string> = {
  PEGGED:   "#22c55e",
  WARNING:  "#facc15",
  DEPEGGED: "#f97316",
  CRITICAL: "#ef4444",
};
const STATUS_ICON: Record<StablecoinPrice["pegStatus"], string> = {
  PEGGED: "✓", WARNING: "⚠", DEPEGGED: "↓", CRITICAL: "🚨",
};

const DEMO_PRICES: StablecoinPrice[] = [
  { id: "usd-coin",   symbol: "USDC",  name: "USD Coin",   price: 0.9998, change24h: 0.01,  pegStatus: "PEGGED"  },
  { id: "tether",     symbol: "USDT",  name: "Tether",     price: 1.0001, change24h: -0.02, pegStatus: "PEGGED"  },
  { id: "dai",        symbol: "DAI",   name: "DAI",        price: 0.9996, change24h: 0.00,  pegStatus: "PEGGED"  },
  { id: "frax",       symbol: "FRAX",  name: "Frax",       price: 0.9821, change24h: -1.2,  pegStatus: "WARNING" },
  { id: "paypal-usd", symbol: "PYUSD", name: "PayPal USD", price: 0.9999, change24h: 0.00,  pegStatus: "PEGGED"  },
];

interface CustomCoin { id: string; symbol: string; name: string; }

export function StablecoinCard() {
  const [prices,      setPrices]      = useState<StablecoinPrice[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [expanded,    setExpanded]    = useState(false);
  const [showAdd,     setShowAdd]     = useState(false);
  const [editMode,    setEditMode]    = useState(false);   // shows remove buttons
  const [customCoins, setCustomCoins] = useState<CustomCoin[]>([]);
  const [coinInput,   setCoinInput]   = useState("");
  const [addLoading,  setAddLoading]  = useState(false);
  const [addError,    setAddError]    = useState("");

  useEffect(() => {
    SecureStore.getItemAsync(CUSTOM_COINS_KEY).then(raw => {
      if (raw) setCustomCoins(JSON.parse(raw));
    });
  }, []);

  useEffect(() => { load(); }, [customCoins.length]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Build extra coin list from customCoins (map to STABLECOINS format)
      const extras = customCoins.map(c => ({
        id: c.id, symbol: c.symbol, name: c.name,
        warn: 0.997, crit: 0.990, repeg: 0.999,
      }));
      const data = await fetchStablecoinPrices(extras);
      setPrices(data);
    } catch {
      setPrices(DEMO_PRICES);
    } finally {
      setLoading(false);
      setLastUpdated(new Date());
    }
  }, [customCoins]);

  async function addCoin() {
    const query = coinInput.trim().toLowerCase();
    if (!query) return;
    setAddLoading(true);
    setAddError("");
    try {
      // Try CoinGecko simple price lookup to validate the ID/symbol
      const url = `https://api.coingecko.com/api/v3/simple/price?ids=${query}&vs_currencies=usd`;
      const resp = await fetch(url);
      const data = await resp.json();
      if (!data[query]?.usd) {
        // Try searching by symbol
        const searchResp = await fetch(`https://api.coingecko.com/api/v3/search?query=${query}`);
        const searchData = await searchResp.json();
        const coin = (searchData.coins ?? []).find(
          (c: any) => c.symbol?.toLowerCase() === query || c.id?.toLowerCase() === query
        );
        if (!coin) throw new Error(`"${coinInput}" not found on CoinGecko. Try the exact CoinGecko ID (e.g. "usd-coin").`);
        const newCoin: CustomCoin = { id: coin.id, symbol: coin.symbol.toUpperCase(), name: coin.name };
        await persistCustom([...customCoins, newCoin]);
      } else {
        // Valid CoinGecko ID used directly
        const newCoin: CustomCoin = { id: query, symbol: query.toUpperCase(), name: query };
        await persistCustom([...customCoins, newCoin]);
      }
      setCoinInput("");
      setShowAdd(false);
    } catch (e: any) {
      setAddError(e.message || "Coin not found — check the CoinGecko ID.");
    }
    setAddLoading(false);
  }

  async function removeCoin(id: string) {
    Alert.alert("Remove coin", "Stop monitoring this stablecoin?", [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => persistCustom(customCoins.filter(c => c.id !== id)) },
    ]);
  }

  async function persistCustom(coins: CustomCoin[]) {
    await SecureStore.setItemAsync(CUSTOM_COINS_KEY, JSON.stringify(coins));
    setCustomCoins(coins);
  }

  const alerts   = prices.filter(p => p.pegStatus !== "PEGGED");
  const critical = prices.filter(p => p.pegStatus === "CRITICAL" || p.pegStatus === "DEPEGGED");
  const shown    = expanded ? prices : prices.slice(0, 3);
  const defaultIds = STABLECOINS.map(s => s.id);

  return (
    <View style={[styles.card, critical.length > 0 && styles.cardCritical]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>💲 Peg &amp; RWA Health Monitor</Text>
          {alerts.length > 0 && (
            <Text style={styles.alertSummary}>
              {critical.length > 0 ? `🚨 ${critical.length} DEPEGGED` : `⚠ ${alerts.length} WARNING`}
            </Text>
          )}
        </View>
        <View style={styles.headerRight}>
          {lastUpdated && (
            <Text style={styles.updated}>{lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</Text>
          )}
          {customCoins.length > 0 && (
            <TouchableOpacity
              onPress={() => setEditMode(e => !e)}
              style={[styles.manageBtn, editMode && styles.manageBtnActive]}
            >
              <Text style={[styles.manageBtnText, editMode && { color: "#ef4444" }]}>
                {editMode ? "Done" : "− Remove"}
              </Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => setShowAdd(true)} style={styles.addBtn}>
            <Text style={styles.addBtnText}>+ Add</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={load} style={styles.refreshBtn}>
            <Text style={styles.refreshIcon}>{loading ? "…" : "↺"}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading && prices.length === 0 ? (
        <ActivityIndicator color="#00B5A5" size="small" style={{ marginVertical: 10 }} />
      ) : (
        <>
          {shown.map(coin => (
            <CoinRow
              key={coin.id}
              coin={coin}
              isCustom={!defaultIds.includes(coin.id)}
              editMode={editMode}
              onRemove={() => removeCoin(coin.id)}
            />
          ))}
          {prices.length > 3 && (
            <TouchableOpacity style={styles.expandBtn} onPress={() => setExpanded(e => !e)}>
              <Text style={styles.expandText}>{expanded ? "Show less ↑" : `Show all ${prices.length} ↓`}</Text>
            </TouchableOpacity>
          )}
        </>
      )}

      {/* Add coin modal */}
      <Modal visible={showAdd} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Add Stablecoin</Text>
            <Text style={styles.modalDesc}>
              Enter a CoinGecko coin ID or symbol to monitor (e.g. "eurc", "usdd", "tusd", "gusd").
            </Text>
            <TextInput
              style={styles.modalInput}
              value={coinInput}
              onChangeText={v => { setCoinInput(v); setAddError(""); }}
              placeholder="e.g. eurc or stasis-eurs"
              placeholderTextColor="#334155"
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={addCoin}
            />
            {addError ? <Text style={styles.addError}>{addError}</Text> : null}
            <View style={styles.modalBtns}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowAdd(false); setCoinInput(""); setAddError(""); }}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={addCoin} disabled={addLoading}>
                {addLoading
                  ? <ActivityIndicator color="#0a1628" size="small" />
                  : <Text style={styles.confirmText}>Add & Monitor</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function CoinRow({ coin, isCustom, editMode, onRemove }: { coin: StablecoinPrice; isCustom: boolean; editMode: boolean; onRemove: () => void }) {
  const color    = STATUS_COLOR[coin.pegStatus];
  const icon     = STATUS_ICON[coin.pegStatus];
  const changeColor = coin.change24h >= 0 ? "#22c55e" : "#ef4444";
  const pctOff   = ((1 - coin.price) * 100).toFixed(3);
  const isOffPeg = coin.pegStatus !== "PEGGED";

  return (
    <View style={[styles.row, isOffPeg && { backgroundColor: color + "08" }]}>
      <View style={styles.rowLeft}>
        <Text style={[styles.statusIcon, { color }]}>{icon}</Text>
        <View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text style={styles.symbol}>{coin.symbol}</Text>
            {isCustom && <Text style={styles.customTag}>custom</Text>}
          </View>
          <Text style={styles.name}>{coin.name}</Text>
        </View>
      </View>
      <View style={styles.rowRight}>
        <Text style={[styles.price, { color: isOffPeg ? color : "#e2e8f0" }]}>
          ${coin.price.toFixed(4)}
        </Text>
        <Text style={[styles.change, { color: changeColor }]}>
          {coin.change24h >= 0 ? "+" : ""}{coin.change24h.toFixed(2)}%
        </Text>
        {isOffPeg && <Text style={[styles.offPeg, { color }]}>{pctOff}% off peg</Text>}
        {isCustom && editMode && (
          <TouchableOpacity onPress={onRemove} style={styles.removeBtn}>
            <Text style={styles.removeText}>✕ Remove</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card:         { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  cardCritical: { borderColor: "#ef444460" },
  header:       { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 },
  title:        { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 2 },
  alertSummary: { fontSize: 11, color: "#ef4444", fontWeight: "700" },
  headerRight:  { flexDirection: "row", alignItems: "center", gap: 8 },
  updated:      { fontSize: 10, color: "#334155" },
  manageBtn:      { backgroundColor: "#ef444415", borderWidth: 1, borderColor: "#ef444430", borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  manageBtnActive:{ backgroundColor: "#ef444425", borderColor: "#ef444460" },
  manageBtnText:  { fontSize: 11, color: "#ef4444", fontWeight: "700" },
  addBtn:       { backgroundColor: "#00B5A510", borderWidth: 1, borderColor: "#00B5A540", borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  addBtnText:   { fontSize: 11, color: "#00B5A5", fontWeight: "700" },
  refreshBtn:   { padding: 4 },
  refreshIcon:  { fontSize: 16, color: "#4a7fa5" },
  row:          { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a", paddingHorizontal: 4, borderRadius: 6, marginBottom: 2 },
  rowLeft:      { flexDirection: "row", alignItems: "center", gap: 10 },
  statusIcon:   { fontSize: 14, width: 18, textAlign: "center" },
  symbol:       { fontSize: 13, fontWeight: "700", color: "#e2e8f0" },
  customTag:    { fontSize: 9, color: "#4a7fa5", backgroundColor: "#1e3a5f", paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  name:         { fontSize: 10, color: "#64748b", marginTop: 1 },
  rowRight:     { alignItems: "flex-end", gap: 2 },
  price:        { fontSize: 13, fontWeight: "700" },
  change:       { fontSize: 10 },
  offPeg:       { fontSize: 10, fontWeight: "700" },
  removeBtn:    { backgroundColor: "#ef444420", borderWidth: 1, borderColor: "#ef444450", borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  removeText:   { fontSize: 10, color: "#ef4444", fontWeight: "700" },
  expandBtn:    { marginTop: 8, alignItems: "center", paddingVertical: 6 },
  expandText:   { fontSize: 11, color: "#4a7fa5" },
  modalOverlay: { flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  modal:        { backgroundColor: "#0F1F3D", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24 },
  modalTitle:   { fontSize: 16, fontWeight: "800", color: "#fff", marginBottom: 6 },
  modalDesc:    { fontSize: 12, color: "#64748b", lineHeight: 18, marginBottom: 14 },
  modalInput:   { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 13, marginBottom: 8 },
  addError:     { fontSize: 11, color: "#ef4444", marginBottom: 8, lineHeight: 16 },
  modalBtns:    { flexDirection: "row", gap: 10, marginTop: 4 },
  cancelBtn:    { flex: 1, backgroundColor: "#1e3a5f", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  cancelText:   { color: "#94a3b8", fontWeight: "600" },
  confirmBtn:   { flex: 2, backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  confirmText:  { color: "#0a1628", fontWeight: "800" },
});
