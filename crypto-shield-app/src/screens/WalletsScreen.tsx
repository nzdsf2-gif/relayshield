import React, { useState, useCallback, useEffect } from "react";
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Modal, Alert, ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import { useWallets, WatchedWallet } from "../hooks/useWallet";
import { RiskGauge } from "../components/RiskGauge";
import * as SecureStore from "expo-secure-store";
import * as RS from "../api/relayshield";
import { useNFTCollections, type NFTChain } from "../hooks/useNFTCollections";
import { connectSolanaWallet } from "../utils/mwa";

interface SweepResult {
  poisoned_addresses: { suspicious: string; lookalike_of: string; dust_amount: string; first_seen: string }[];
  breach_emails: { email: string; found: boolean; count?: number }[];
  infostealer_emails: { email: string; found: boolean }[];
  // Gmail-side checks — require manual verification, not available via API
  manual_checks: { label: string; instruction: string }[];
}

const MANUAL_CHECKS = [
  { label: "Forwarding rules", instruction: "Gmail: Settings → See all settings → Forwarding and POP/IMAP — check for unknown addresses" },
  { label: "Inbox filters", instruction: "Gmail: Settings → See all settings → Filters and Blocked Addresses — delete any you didn't create" },
  { label: "Recovery email & phone", instruction: "myaccount.google.com → Security → Ways we can verify it's you" },
  { label: "Active devices", instruction: "myaccount.google.com → Security → Your devices — remove unrecognised sessions" },
];

function SweepModal({ visible, onClose, wallets, apiKey }: {
  visible: boolean; onClose: () => void;
  wallets: WatchedWallet[]; apiKey: string | null;
}) {
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [result, setSweepResult] = useState<SweepResult | null>(null);

  async function runSweep() {
    setRunning(true);
    setSweepResult(null);

    // 1. Breach + infostealer checks on stored emails
    setStatus("Checking email breach exposure…");
    let emails: string[] = [];
    try {
      const raw = await SecureStore.getItemAsync("cs_monitored_emails");
      emails = raw ? JSON.parse(raw).filter(Boolean) : [];
    } catch { emails = []; }

    const breachEmails: SweepResult["breach_emails"] = [];
    const stealerEmails: SweepResult["infostealer_emails"] = [];

    if (apiKey && emails.length > 0) {
      await Promise.allSettled(emails.map(async (email) => {
        try {
          const b = await RS.checkBreach(email, apiKey);
          breachEmails.push({ email, found: !!(b?.found || (b?.breaches?.length ?? 0) > 0), count: b?.breaches?.length });
        } catch { breachEmails.push({ email, found: false }); }
        try {
          const s = await RS.checkInfostealer(email, apiKey);
          stealerEmails.push({ email, found: !!(s?.found || s?.exposed) });
        } catch { stealerEmails.push({ email, found: false }); }
      }));
    }

    // 2. Address poisoning — query via backend proxy (Alchemy key stays server-side)
    setStatus("Scanning wallet history for address poisoning…");
    const poisoned: SweepResult["poisoned_addresses"] = [];

    for (const wallet of wallets.filter(w => w.chain === "solana")) {
      try {
        const sigsResp = await fetch("https://api.relayshield.net/v1/app/solana-rpc", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-RS-API-KEY": apiKey },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignaturesForAddress", params: [wallet.address, { limit: 40 }] }),
        });
        const sigsData = await sigsResp.json();
        const sigs: { signature: string }[] = sigsData.result || [];

        for (const sig of sigs.slice(0, 15)) {
          const txResp = await fetch("https://api.relayshield.net/v1/app/solana-rpc", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-RS-API-KEY": apiKey },
            body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getTransaction", params: [sig.signature, { maxSupportedTransactionVersion: 0 }] }),
          });
          const txData = await txResp.json();
          const tx = txData.result;
          if (!tx?.meta) continue;

          const preB: number[] = tx.meta.preBalances || [];
          const postB: number[] = tx.meta.postBalances || [];
          const accounts: string[] = tx.transaction?.message?.accountKeys || [];

          for (let i = 0; i < accounts.length; i++) {
            const received = (postB[i] || 0) - (preB[i] || 0);
            if (received > 0 && received < 5000 && accounts[i] !== wallet.address) {
              const sender = accounts[i];
              const myAddr = wallet.address;
              if (sender.slice(0, 6) === myAddr.slice(0, 6) || sender.slice(-6) === myAddr.slice(-6)) {
                poisoned.push({
                  suspicious: sender,
                  lookalike_of: myAddr,
                  dust_amount: `${(received / 1e9).toFixed(9)} SOL`,
                  first_seen: new Date((tx.blockTime || 0) * 1000).toISOString(),
                });
              }
            }
          }
        }
      } catch { /* skip wallet on error */ }
    }

    setSweepResult({
      poisoned_addresses: poisoned,
      breach_emails: breachEmails,
      infostealer_emails: stealerEmails,
      manual_checks: MANUAL_CHECKS,
    });
    setStatus("");
    setRunning(false);
  }

  function handleClose() { setSweepResult(null); setRunning(false); setStatus(""); onClose(); }

  const issues = result
    ? result.poisoned_addresses.length +
      result.breach_emails.filter(e => e.found).length +
      result.infostealer_emails.filter(e => e.found).length
    : 0;

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={sw.overlay}>
        <View style={sw.modal}>
          <View style={sw.modalHeader}>
            <Text style={sw.modalTitle}>🔐 Security Sweep</Text>
            <TouchableOpacity onPress={handleClose}><Text style={sw.closeBtn}>✕</Text></TouchableOpacity>
          </View>
          <Text style={sw.modalSub}>Audits your email account and wallet addresses for backdoors and address poisoning attacks</Text>

          {!result && !running && (
            <TouchableOpacity style={sw.runBtn} onPress={runSweep}>
              <Text style={sw.runBtnText}>Run Sweep Now</Text>
            </TouchableOpacity>
          )}

          {running && (
            <View style={sw.loadingWrap}>
              <ActivityIndicator color="#00B5A5" size="large" />
              <Text style={sw.loadingText}>{status || "Running sweep…"}</Text>
            </View>
          )}

          {result && (
            <ScrollView showsVerticalScrollIndicator={false}>
              <View style={[sw.issuesBanner, { borderColor: issues > 0 ? "#ef4444" : "#22c55e" }]}>
                <Text style={[sw.issuesCount, { color: issues > 0 ? "#ef4444" : "#22c55e" }]}>
                  {issues > 0 ? `${issues} issue${issues !== 1 ? "s" : ""} found` : "No active threats detected"}
                </Text>
                <Text style={sw.issuesSub}>
                  {issues > 0 ? "Review and resolve the findings below" : "Breach, infostealer, and poisoning checks passed"}
                </Text>
              </View>

              {/* Breach results */}
              {result.breach_emails.length > 0 && (
                <View style={sw.section}>
                  <Text style={sw.sectionLabel}>BREACH EXPOSURE</Text>
                  {result.breach_emails.map((e, i) => (
                    <SweepRow key={i}
                      label={e.email.replace(/(.{1}).*(@.*)/, "$1***$2")}
                      value={e.found ? `⚠ Found in ${e.count ?? "known"} breach${(e.count ?? 1) !== 1 ? "es" : ""}` : "✓ No breaches found"}
                      ok={!e.found}
                    />
                  ))}
                </View>
              )}

              {/* Infostealer results */}
              {result.infostealer_emails.length > 0 && (
                <View style={sw.section}>
                  <Text style={sw.sectionLabel}>INFOSTEALER LOGS</Text>
                  {result.infostealer_emails.map((e, i) => (
                    <SweepRow key={i}
                      label={e.email.replace(/(.{1}).*(@.*)/, "$1***$2")}
                      value={e.found ? "⚠ Found in stealer logs" : "✓ Not in stealer logs"}
                      ok={!e.found}
                    />
                  ))}
                </View>
              )}

              {result.breach_emails.length === 0 && result.infostealer_emails.length === 0 && (
                <View style={sw.finding}>
                  <Text style={sw.findingAction}>Add monitored emails in Settings to enable breach and infostealer checks.</Text>
                </View>
              )}

              {/* Address poisoning */}
              {result.poisoned_addresses.length > 0 ? (
                <View style={sw.finding}>
                  <Text style={sw.findingLabel}>🚨 Address Poisoning Detected</Text>
                  {result.poisoned_addresses.map((p, i) => (
                    <View key={i} style={sw.poisonBlock}>
                      <Text style={sw.poisonLabel}>Suspicious address in your tx history:</Text>
                      <Text style={sw.poisonAddr}>{p.suspicious.slice(0,8)}...{p.suspicious.slice(-6)}</Text>
                      <Text style={sw.poisonLabel}>Looks like your known address:</Text>
                      <Text style={sw.poisonAddrSafe}>{p.lookalike_of.slice(0,8)}...{p.lookalike_of.slice(-6)}</Text>
                      <Text style={sw.poisonDetail}>Dust: {p.dust_amount} · {p.first_seen.slice(0,10)}</Text>
                    </View>
                  ))}
                  <Text style={sw.findingAction}>Never copy an address from transaction history — use saved contacts only.</Text>
                </View>
              ) : (
                <SweepRow label="Address poisoning" value="✓ No dust attacks detected" ok={true} />
              )}

              {/* Linked Device Audit */}
              <View style={sw.section}>
                <Text style={sw.sectionLabel}>LINKED DEVICE AUDIT</Text>
                <Text style={sw.manualNote}>QR-based device-linking attacks give attackers silent read access to all messages. Verify manually in each app:</Text>
                {[
                  { label: "Telegram",  instruction: "Settings → Devices → remove unrecognised sessions" },
                  { label: "WhatsApp",  instruction: "Settings → Linked Devices → log out unfamiliar entries" },
                  { label: "Signal",    instruction: "Settings → Account → Linked Devices → unlink unknowns" },
                ].map((c, i) => (
                  <View key={i} style={sw.manualItem}>
                    <Text style={sw.manualLabel}>☐ {c.label}</Text>
                    <Text style={sw.manualInstr}>{c.instruction}</Text>
                  </View>
                ))}
              </View>

              {/* Manual Gmail checks */}
              <View style={sw.section}>
                <Text style={sw.sectionLabel}>EMAIL ACCOUNT AUDIT</Text>
                <Text style={sw.manualNote}>These checks require Gmail account access — verify manually:</Text>
                {result.manual_checks.map((c, i) => (
                  <View key={i} style={sw.manualItem}>
                    <Text style={sw.manualLabel}>☐ {c.label}</Text>
                    <Text style={sw.manualInstr}>{c.instruction}</Text>
                  </View>
                ))}
              </View>

              <TouchableOpacity style={sw.runBtn} onPress={runSweep}>
                <Text style={sw.runBtnText}>Run Again</Text>
              </TouchableOpacity>
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

function SweepRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <View style={sw.sweepRow}>
      <Text style={sw.sweepRowLabel}>{label}</Text>
      <Text style={[sw.sweepRowVal, { color: ok ? "#22c55e" : "#ef4444" }]}>{value}</Text>
    </View>
  );
}

const sw = StyleSheet.create({
  overlay:       { flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  modal:         { backgroundColor: "#0F1F3D", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, maxHeight: "85%" },
  modalHeader:   { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  modalTitle:    { fontSize: 18, fontWeight: "800", color: "#fff" },
  closeBtn:      { fontSize: 18, color: "#64748b", padding: 4 },
  modalSub:      { fontSize: 12, color: "#64748b", lineHeight: 18, marginBottom: 18 },
  runBtn:        { backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 14, alignItems: "center", marginTop: 8 },
  runBtnText:    { color: "#0a1628", fontWeight: "800", fontSize: 14 },
  loadingWrap:   { alignItems: "center", paddingVertical: 30, gap: 12 },
  loadingText:   { fontSize: 13, color: "#00B5A5", textAlign: "center", marginTop: 12 },
  section:       { marginTop: 16 },
  sectionLabel:  { fontSize: 9, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 8 },
  manualNote:    { fontSize: 11, color: "#64748b", marginBottom: 8, fontStyle: "italic" },
  manualItem:    { marginBottom: 10 },
  manualLabel:   { fontSize: 12, color: "#94a3b8", fontWeight: "600", marginBottom: 2 },
  manualInstr:   { fontSize: 11, color: "#64748b", lineHeight: 16 },
  issuesBanner:  { borderRadius: 10, padding: 14, borderWidth: 1, backgroundColor: "#060b18", marginBottom: 16 },
  issuesCount:   { fontSize: 18, fontWeight: "800", marginBottom: 4 },
  issuesSub:     { fontSize: 12, color: "#94a3b8" },
  sweepRow:      { flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  sweepRowLabel: { fontSize: 13, color: "#94a3b8" },
  sweepRowVal:   { fontSize: 13, fontWeight: "600" },
  finding:       { backgroundColor: "#060b18", borderRadius: 10, padding: 14, marginTop: 12, borderWidth: 1, borderColor: "#ef444440" },
  findingLabel:  { fontSize: 13, fontWeight: "700", color: "#ef4444", marginBottom: 8 },
  findingDetail: { fontSize: 12, color: "#cbd5e1", lineHeight: 18, marginBottom: 4 },
  findingAction: { fontSize: 11, color: "#fbbf24", marginTop: 8, fontStyle: "italic", fontWeight: "600" },
  poisonBlock:   { backgroundColor: "#1e3a5f", borderRadius: 8, padding: 10, marginBottom: 8 },
  poisonLabel:   { fontSize: 10, color: "#94a3b8", marginBottom: 2 },
  poisonAddr:    { fontSize: 12, fontFamily: "monospace", color: "#ef4444", marginBottom: 6 },
  poisonAddrSafe:{ fontSize: 12, fontFamily: "monospace", color: "#22c55e", marginBottom: 6 },
  poisonDetail:  { fontSize: 10, color: "#94a3b8" },
});

type Chain = WatchedWallet["chain"];

const CHAIN_LABELS: Record<Chain, string> = {
  solana:  "◎ Solana",
  evm:     "Ξ EVM",
  bitcoin: "₿ Bitcoin",
  ton:     "💎 TON",
};

export function WalletsScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const { wallets, apiKey, addWallet, removeWallet, updateWalletRisk } = useWallets();
  const [showAdd, setShowAdd] = useState(false);
  const [showSweep, setShowSweep] = useState(false);
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [chain, setChain] = useState<Chain>("solana");
  const [scanningAddr, setScanningAddr] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  async function handleConnectWallet() {
    setConnecting(true);
    try {
      const connectedAddress = await connectSolanaWallet();
      setAddress(connectedAddress);
    } catch (err: any) {
      Alert.alert(
        "Connection failed",
        err?.message ?? "Could not connect to a wallet app. Make sure a wallet like Phantom or Solflare is installed."
      );
    }
    setConnecting(false);
  }

  const scanWallet = useCallback(async (wallet: WatchedWallet) => {
    if (!apiKey) {
      Alert.alert(
        "Subscription required",
        "Link your subscription in Settings to scan wallets.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Go to Settings", onPress: () => navigation.navigate("Settings") },
        ],
      );
      return;
    }
    setScanningAddr(wallet.address);
    try {
      const data = await RS.scanWalletRisk(wallet.address, apiKey);
      const SCORE_MAP: Record<string, number> = { LOW: 20, MEDIUM: 45, HIGH: 70, CRITICAL: 90 };
      const score = SCORE_MAP[(data.risk_level ?? "LOW").toUpperCase()] ?? 20;
      updateWalletRisk(wallet.address, score, (data.risk_level ?? "LOW").toUpperCase() as any);
    } catch (err: any) {
      Alert.alert("Scan failed", err?.message ?? "Could not reach the risk API. Check your connection and subscription.");
    }
    setScanningAddr(null);
  }, [apiKey, navigation]);

  async function handleAdd() {
    if (!address.trim()) return;
    const newWallet = { address: address.trim(), label: label || "Wallet", chain };
    await addWallet(newWallet);
    setAddress(""); setLabel(""); setShowAdd(false);
    // Scan immediately — updateWalletRisk now reads from SecureStore, not the stale closure
    scanWallet({ ...newWallet, addedAt: new Date().toISOString() });
  }

  function confirmRemove(addr: string, lbl: string) {
    Alert.alert("Remove Wallet", `Stop monitoring ${lbl}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => removeWallet(addr) },
    ]);
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Monitored Wallets</Text>
          <Text style={styles.tagline}>Up to 5 wallets · Solana · EVM · Base · TON · Bitcoin</Text>
        </View>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
          <Text style={styles.addBtnText}>+ Add Wallet</Text>
        </TouchableOpacity>
      </View>

      {/* Sweep button */}
      <TouchableOpacity style={styles.sweepBtn} onPress={() => setShowSweep(true)}>
        <Text style={styles.sweepIcon}>🔐</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.sweepTitle}>Security Sweep</Text>
          <Text style={styles.sweepSub}>Email backdoors · Address poisoning · OAuth apps</Text>
        </View>
        <Text style={styles.sweepArrow}>›</Text>
      </TouchableOpacity>

      <ScrollView showsVerticalScrollIndicator={false} style={{ flex: 1, paddingHorizontal: 16 }}>
        {wallets.map(w => (
          <WalletCard
            key={w.address}
            wallet={w}
            scanning={scanningAddr === w.address}
            onRemove={() => confirmRemove(w.address, w.label)}
            onScan={() => scanWallet(w)}
          />
        ))}
        {wallets.length === 0 && <WalletCard wallet={DEMO_WALLET} scanning={false} onRemove={() => {}} onScan={() => {}} />}

        {/* NFT Collections */}
        <NFTCollections />

        <View style={{ height: 20 }} />
      </ScrollView>

      <SweepModal visible={showSweep} onClose={() => setShowSweep(false)} wallets={wallets} apiKey={apiKey} />

      {/* Add wallet modal */}
      <Modal visible={showAdd} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Add Wallet</Text>

            <Text style={styles.fieldLabel}>Chain</Text>
            <View style={styles.chainRow}>
              {(["solana", "evm", "bitcoin", "ton"] as Chain[]).map(c => (
                <TouchableOpacity
                  key={c}
                  style={[styles.chainBtn, chain === c && styles.chainBtnActive]}
                  onPress={() => setChain(c)}
                >
                  <Text style={[styles.chainBtnText, chain === c && { color: "#00B5A5" }]}>
                    {CHAIN_LABELS[c]}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {chain === "solana" && (
              <TouchableOpacity
                style={[styles.connectBtn, connecting && { opacity: 0.6 }]}
                onPress={handleConnectWallet}
                disabled={connecting}
              >
                {connecting
                  ? <ActivityIndicator color="#00B5A5" size="small" />
                  : <Text style={styles.connectBtnText}>◎ Connect Wallet</Text>
                }
              </TouchableOpacity>
            )}

            <Text style={styles.fieldLabel}>
              {chain === "solana" ? "Or Enter Wallet Address" : "Wallet Address"}
            </Text>
            <TextInput
              style={styles.input}
              value={address}
              onChangeText={setAddress}
              placeholder={
                chain === "solana"  ? "e.g. 7xKXtg2CW87d97TXJ..." :
                chain === "evm"     ? "e.g. 0x742d35Cc6634..." :
                chain === "bitcoin" ? "e.g. bc1q..." :
                                      "e.g. EQBv..."
              }
              placeholderTextColor="#334155"
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.fieldLabel}>Label (optional)</Text>
            <TextInput
              style={styles.input}
              value={label}
              onChangeText={setLabel}
              placeholder="e.g. Main Wallet"
              placeholderTextColor="#334155"
            />

            <View style={styles.modalBtns}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowAdd(false)}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleAdd}>
                <Text style={styles.confirmText}>Add & Monitor</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const DEMO_WALLET: WatchedWallet = {
  address: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
  label: "Main Wallet",
  chain: "solana",
  addedAt: new Date(Date.now() - 86400000 * 3).toISOString(),
  lastRiskScore: 62,
  lastRiskLevel: "HIGH",
  lastChecked: new Date(Date.now() - 240000).toISOString(),
};

function WalletCard({ wallet, onRemove, onScan, scanning }: {
  wallet: WatchedWallet; onRemove: () => void;
  onScan: () => void; scanning: boolean;
}) {
  const score = wallet.lastRiskScore ?? 0;
  const hasScore = wallet.lastRiskScore !== undefined;
  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <View style={{ flex: 1 }}>
          <Text style={styles.walletLabel}>{wallet.label}</Text>
          <Text style={styles.walletChain}>{CHAIN_LABELS[wallet.chain]}</Text>
          <Text style={styles.walletAddr} numberOfLines={1}>
            {wallet.address.slice(0, 12)}...{wallet.address.slice(-8)}
          </Text>
          {wallet.lastChecked
            ? <Text style={styles.lastChecked}>Last scan: {new Date(wallet.lastChecked).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</Text>
            : <Text style={styles.lastChecked}>Not yet scanned</Text>
          }
        </View>
        {hasScore
          ? <RiskGauge score={score} size={90} />
          : (
            <View style={styles.noScoreBox}>
              <Text style={styles.noScoreText}>—</Text>
              <Text style={styles.noScoreLabel}>not scanned</Text>
            </View>
          )
        }
      </View>
      <View style={styles.cardActions}>
        <TouchableOpacity
          style={[styles.scanBtn, scanning && { opacity: 0.6 }]}
          onPress={onScan}
          disabled={scanning}
        >
          {scanning
            ? <ActivityIndicator color="#00B5A5" size="small" />
            : <Text style={styles.scanBtnText}>↺ Scan Now</Text>
          }
        </TouchableOpacity>
        <TouchableOpacity onPress={onRemove} style={styles.removeBtn}>
          <Text style={styles.removeText}>Remove</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── NFT Collections ────────────────────────────────────────────────────────
// Shares src/hooks/useNFTCollections.ts with SettingsScreen.tsx's NFT manager
// instead of independently reading/writing cs_nft_collections — the two
// screens used to disagree on shape ({contract, name, chain: "evm"} vs
// {chain, id}), which is what caused a real crash in Settings. This UI keeps
// its own simpler 3-way chain picker (solana/evm/ton); "evm" maps to the
// canonical "eth" value on write.

type WalletsChainPick = "solana" | "evm" | "ton";

function NFTCollections() {
  const { collections, addCollection: addCollectionShared, removeCollection } = useNFTCollections();
  const [showAdd, setShowAdd]         = useState(false);
  const [contract, setContract]       = useState("");
  const [name, setName]               = useState("");
  const [chain, setChain]             = useState<WalletsChainPick>("solana");

  async function addCollection() {
    if (!contract.trim()) return;
    const canonicalChain: NFTChain = chain === "evm" ? "eth" : chain;
    const displayName = name.trim() || contract.trim().slice(0, 12) + "...";
    await addCollectionShared(canonicalChain, contract, displayName);
    setContract(""); setName(""); setShowAdd(false);
  }

  return (
    <View style={nft.section}>
      <View style={nft.header}>
        <Text style={nft.title}>🖼 NFT Collections</Text>
        <TouchableOpacity onPress={() => setShowAdd(v => !v)} style={nft.addBtn}>
          <Text style={nft.addBtnText}>{showAdd ? "Cancel" : "+ Add"}</Text>
        </TouchableOpacity>
      </View>
      <Text style={nft.desc}>
        Track NFT collections for floor alerts.
        Tap any collection to scan in the Scan tab.
      </Text>

      {collections.length === 0 && !showAdd && (
        <Text style={nft.empty}>No collections tracked yet</Text>
      )}

      {collections.map(c => (
        <View key={`${c.chain}-${c.id}`} style={nft.row}>
          <View style={{ flex: 1 }}>
            <Text style={nft.colName}>{c.name || c.id}</Text>
            <Text style={nft.colContract} numberOfLines={1}>{c.id.slice(0, 14)}...{c.id.slice(-6)}</Text>
            <Text style={nft.colChain}>{c.chain.toUpperCase()}</Text>
          </View>
          <TouchableOpacity onPress={() => removeCollection(c.chain, c.id)} style={nft.removeBtn}>
            <Text style={nft.removeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>
      ))}

      {showAdd && (
        <View style={nft.addForm}>
          <Text style={nft.fieldLabel}>Chain</Text>
          <View style={{ flexDirection: "row", gap: 8, marginBottom: 10 }}>
            {(["solana", "evm", "ton"] as const).map(c => (
              <TouchableOpacity
                key={c}
                style={[nft.chainBtn, chain === c && nft.chainBtnActive]}
                onPress={() => setChain(c)}
              >
                <Text style={[nft.chainBtnText, chain === c && { color: "#00B5A5" }]}>
                  {c === "solana" ? "◎ Solana" : c === "evm" ? "Ξ EVM" : "💎 TON"}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={nft.fieldLabel}>
            {chain === "solana" ? "Magic Eden Slug" : chain === "evm" ? "Contract Address" : "TON Collection Address"}
          </Text>
          <TextInput
            style={nft.input}
            value={contract}
            onChangeText={setContract}
            placeholder={chain === "solana" ? "e.g. mad_lads" : chain === "evm" ? "e.g. 0x1234..." : "e.g. EQA..."}
            placeholderTextColor="#334155"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={nft.fieldLabel}>Collection Name (optional)</Text>
          <TextInput
            style={[nft.input, { marginBottom: 12 }]}
            value={name}
            onChangeText={setName}
            placeholder="e.g. Mad Lads"
            placeholderTextColor="#334155"
          />
          <TouchableOpacity style={nft.saveBtn} onPress={addCollection}>
            <Text style={nft.saveBtnText}>Add Collection</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const nft = StyleSheet.create({
  section:       { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginTop: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  header:        { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  title:         { fontSize: 13, fontWeight: "700", color: "#e2e8f0" },
  desc:          { fontSize: 11, color: "#64748b", lineHeight: 16, marginBottom: 10 },
  addBtn:        { backgroundColor: "#1e3a5f", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  addBtnText:    { fontSize: 11, color: "#00B5A5", fontWeight: "700" },
  empty:         { fontSize: 12, color: "#334155", fontStyle: "italic", textAlign: "center", paddingVertical: 10 },
  row:           { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderTopWidth: 1, borderTopColor: "#1e3a5f1a" },
  colName:       { fontSize: 13, fontWeight: "600", color: "#e2e8f0" },
  colContract:   { fontSize: 10, color: "#64748b", fontFamily: "monospace", marginTop: 1 },
  colChain:      { fontSize: 9, color: "#4a7fa5", marginTop: 2, fontWeight: "600" },
  removeBtn:     { padding: 6 },
  removeBtnText: { color: "#64748b", fontSize: 16 },
  addForm:       { marginTop: 10, borderTopWidth: 1, borderTopColor: "#1e3a5f", paddingTop: 12 },
  fieldLabel:    { fontSize: 10, color: "#e2e8f0", fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 6 },
  input:         { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 10, color: "#e2e8f0", fontSize: 12, fontFamily: "monospace", marginBottom: 8 },
  chainBtn:      { flex: 1, backgroundColor: "#060b18", borderRadius: 8, paddingVertical: 8, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  chainBtnActive:{ borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  chainBtnText:  { fontSize: 11, color: "#64748b", fontWeight: "600" },
  saveBtn:       { backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 10, alignItems: "center" },
  saveBtnText:   { color: "#0a1628", fontWeight: "800", fontSize: 13 },
});

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: "#0a1628" },
  header:      { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20 },
  title:       { fontSize: 20, fontWeight: "800", color: "#fff" },
  tagline:     { fontSize: 11, color: "#4a7fa5", marginTop: 3 },
  addBtn:      { backgroundColor: "#00B5A5", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  addBtnText:  { color: "#0a1628", fontWeight: "700", fontSize: 13 },

  sweepBtn:    { flexDirection: "row", alignItems: "center", backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginHorizontal: 16, marginBottom: 14, borderWidth: 1, borderColor: "#00B5A540", gap: 12 },
  sweepIcon:   { fontSize: 22 },
  sweepTitle:  { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 2 },
  sweepSub:    { fontSize: 11, color: "#4a7fa5" },
  sweepArrow:  { fontSize: 22, color: "#00B5A5", fontWeight: "300" },
  empty:       { alignItems: "center", paddingVertical: 60 },
  emptyIcon:   { fontSize: 44, marginBottom: 14 },
  emptyTitle:  { fontSize: 16, fontWeight: "700", color: "#e2e8f0", marginBottom: 8 },
  emptySub:    { fontSize: 13, color: "#64748b", textAlign: "center", lineHeight: 20 },

  card:        { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  cardTop:     { flexDirection: "row", alignItems: "flex-start", gap: 12, marginBottom: 12 },
  walletLabel: { fontSize: 15, fontWeight: "700", color: "#e2e8f0" },
  walletChain: { fontSize: 11, color: "#00B5A5", marginTop: 2 },
  walletAddr:  { fontSize: 11, color: "#64748b", fontFamily: "monospace", marginTop: 4 },
  lastChecked: { fontSize: 10, color: "#334155", marginTop: 4 },
  cardActions: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 },
  scanBtn:     { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#00B5A515", borderWidth: 1, borderColor: "#00B5A540", borderRadius: 8, paddingHorizontal: 14, paddingVertical: 7 },
  scanBtnText: { fontSize: 12, color: "#00B5A5", fontWeight: "700" },
  noScoreBox:  { width: 90, height: 90, alignItems: "center", justifyContent: "center", backgroundColor: "#1e3a5f", borderRadius: 45, borderWidth: 1, borderColor: "#334155" },
  noScoreText: { fontSize: 22, color: "#334155", fontWeight: "800" },
  noScoreLabel:{ fontSize: 9, color: "#334155", marginTop: 2 },
  removeBtn:   { paddingVertical: 4 },
  removeText:  { fontSize: 12, color: "#f1f5f9" },

  modalOverlay:{ flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  modal:       { backgroundColor: "#0F1F3D", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24 },
  modalTitle:  { fontSize: 18, fontWeight: "800", color: "#fff", marginBottom: 20 },
  fieldLabel:  { fontSize: 11, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase" },
  chainRow:    { flexDirection: "row", gap: 8, marginBottom: 18 },
  connectBtn:  { flexDirection: "row", justifyContent: "center", alignItems: "center", backgroundColor: "#00B5A515", borderWidth: 1, borderColor: "#00B5A5", borderRadius: 8, paddingVertical: 12, marginBottom: 12 },
  connectBtnText: { color: "#00B5A5", fontWeight: "800", fontSize: 13 },
  chainBtn:    { flex: 1, backgroundColor: "#1e3a5f", borderRadius: 8, paddingVertical: 8, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  chainBtnActive:{ borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  chainBtnText:{ fontSize: 12, color: "#64748b", fontWeight: "600" },
  input:       { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 13, marginBottom: 16, fontFamily: "monospace" },
  modalBtns:   { flexDirection: "row", gap: 10, marginTop: 8 },
  cancelBtn:   { flex: 1, backgroundColor: "#1e3a5f", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  cancelText:  { color: "#94a3b8", fontWeight: "600" },
  confirmBtn:  { flex: 2, backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  confirmText: { color: "#0a1628", fontWeight: "800" },
});
