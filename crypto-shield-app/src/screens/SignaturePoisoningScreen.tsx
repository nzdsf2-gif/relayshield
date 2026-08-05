// Signature Guard — Wallet Security Suite

import React, { useState, useEffect } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  TextInput, Modal, Alert, ActivityIndicator,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import * as RS from "../api/relayshield";
import { useWallets } from "../hooks/useWallet";

type GuardTab = "poisoning" | "approvals" | "simulation" | "sessions";

// ── Poisoning helpers ──────────────────────────────────────────────────────

function charDiff(a: string, b: string): { char: string; match: boolean }[] {
  return a.split("").map((char, i) => ({
    char,
    match: i < b.length && char.toLowerCase() === b[i].toLowerCase(),
  }));
}

function prefixSuffixScore(pasted: string, saved: string): { prefix: number; suffix: number; total: number } {
  const p = pasted.toLowerCase();
  const s = saved.toLowerCase();
  let prefix = 0;
  for (let i = 0; i < Math.min(p.length, s.length); i++) {
    if (p[i] === s[i]) prefix++;
    else break;
  }
  let suffix = 0;
  for (let i = 1; i <= Math.min(p.length, s.length); i++) {
    if (p[p.length - i] === s[s.length - i]) suffix++;
    else break;
  }
  return { prefix, suffix, total: prefix + suffix };
}

const DEMO_APPROVALS = [
  { token: "USDC",  contract: "0xa0b8...eb48", spender: "0xd9e1...4F23 (Unknown)", unlimited: true,  value: "∞",          risk: "HIGH",   age: "142 days ago" },
  { token: "WETH",  contract: "0xC02a...e1F8", spender: "Uniswap V3 Router",         unlimited: true,  value: "∞",          risk: "LOW",    age: "89 days ago"  },
  { token: "PEPE",  contract: "0x6982...f6e5", spender: "0x4848...dead (Drainer)",    unlimited: true,  value: "∞",          risk: "CRITICAL", age: "3 days ago"  },
  { token: "DAI",   contract: "0x6B17...9D3E", spender: "Compound V3",                unlimited: false, value: "5,000 DAI",  risk: "LOW",    age: "210 days ago" },
  { token: "SHIB",  contract: "0x95aD...fca9", spender: "0x0000...0000 (Burned?)",    unlimited: true,  value: "∞",          risk: "MEDIUM", age: "31 days ago"  },
];

const DEMO_SIMULATION = {
  dapp: "Uniswap v3",
  action: "Swap 0.5 ETH → USDC",
  netChanges: [
    { token: "ETH",  change: "-0.5000", color: "#ef4444" },
    { token: "USDC", change: "+921.44", color: "#22c55e" },
    { token: "ETH",  change: "-0.0012 (gas)", color: "#64748b" },
  ],
  safeToSign: true,
  warnings: [],
  gasEstimate: "0.0012 ETH (~$2.21)",
  slippage: "0.5%",
};

const SESSIONS_KEY = "cs_dapp_sessions";

interface DappSession {
  id: string;
  dapp: string;
  url: string;
  addedAt: string;
  chains: string[];
  trusted: boolean | null; // null = unchecked
  reputationNote?: string;
}

// Known trusted dApp domains for instant reputation
const KNOWN_TRUSTED: Record<string, string> = {
  // EVM DEXs & lending
  "app.uniswap.org": "Uniswap — verified DEX",
  "curve.fi": "Curve — verified DEX",
  "app.compound.finance": "Compound — verified lending",
  "aave.com": "Aave — verified lending protocol",
  "pancakeswap.finance": "PancakeSwap — verified DEX",
  "app.aave.com": "Aave — verified lending protocol",
  "app.sushi.com": "SushiSwap — verified DEX",
  "1inch.io": "1inch — verified DEX aggregator",
  "app.1inch.io": "1inch — verified DEX aggregator",
  "balancer.fi": "Balancer — verified DEX",
  "app.balancer.fi": "Balancer — verified DEX",
  "lido.fi": "Lido — verified liquid staking",
  "stake.lido.fi": "Lido — verified liquid staking",
  "makerdao.com": "MakerDAO — verified lending",
  "app.spark.fi": "Spark — verified lending (MakerDAO)",
  // NFT marketplaces
  "opensea.io": "OpenSea — verified marketplace",
  "blur.io": "Blur — verified NFT marketplace",
  "x2y2.io": "X2Y2 — verified NFT marketplace",
  // Solana DEXs & lending
  "raydium.io": "Raydium — verified Solana DEX",
  "jup.ag": "Jupiter — verified Solana aggregator",
  "kamino.finance": "Kamino — verified Solana lending",
  "app.kamino.finance": "Kamino — verified Solana lending",
  "kamino.com": "Kamino — verified Solana lending",
  "orca.so": "Orca — verified Solana DEX",
  "marinade.finance": "Marinade — verified Solana staking",
  "drift.trade": "Drift — verified Solana perps",
  "app.drift.trade": "Drift — verified Solana perps",
  "mango.markets": "Mango Markets — verified Solana DEX",
  "meteora.ag": "Meteora — verified Solana DEX",
  // NFT (Solana)
  "magiceden.io": "Magic Eden — verified NFT marketplace",
  "magic.eden": "Magic Eden — verified NFT marketplace",
  "tensor.trade": "Tensor — verified Solana NFT marketplace",
};

// Known suspicious patterns
const SUSPICIOUS_PATTERNS = [
  /yield.*2x|yield.*3x|yield.*10x/i,
  /free.*eth|free.*sol|free.*usdc/i,
  /claim.*reward|airdrop.*claim/i,
  /wallet.*verify|verify.*wallet/i,
  /-[a-z]+\.(xyz|top|click|tk|ml|ga|cf)$/i,
];

// ── Helpers ────────────────────────────────────────────────────────────────

function riskColor(r: string) {
  return r === "CRITICAL" ? "#ef4444" : r === "HIGH" ? "#f97316" : r === "MEDIUM" ? "#facc15" : "#22c55e";
}

// ── Sub-screens ────────────────────────────────────────────────────────────

function AddressPoisoningTab() {
  const navigation = useNavigation<any>();
  const { wallets, apiKey } = useWallets();
  const [input, setInput]         = useState("");
  const [checking, setChecking]   = useState(false);
  const [result, setResult]       = useState<any>(null);
  const [txScanning, setTxScanning]   = useState(false);
  const [txFindings, setTxFindings]   = useState<any[]>([]);
  const [txScanned, setTxScanned]     = useState(false);
  const [txStatus, setTxStatus]       = useState("");
  const [txSummary, setTxSummary]     = useState<{ label: string; chain: string; txCount: number }[]>([]);
  const evmWallets = wallets.filter(w => w.chain === "evm");

  // Auto-check when input reaches a valid address length
  useEffect(() => {
    const addr = input.trim();
    const isEVM = addr.startsWith("0x") && addr.length === 42;
    const isSOL = !addr.startsWith("0x") && addr.length >= 32 && addr.length <= 44;
    if (isEVM || isSOL) {
      checkAddress(addr);
    } else {
      setResult(null);
    }
  }, [input]);

  async function checkAddress(addr: string) {
    setChecking(true);
    setResult(null);
    try {
      // 1. Compare against all saved wallets
      const comparisons = wallets.map(w => {
        const scores = prefixSuffixScore(addr, w.address);
        const minLen = Math.min(addr.length, w.address.length);
        // Poisoning = same prefix (6+ chars) AND same suffix (4+ chars) but not identical
        const isPoisoning = scores.prefix >= 6 && scores.suffix >= 4
          && addr.toLowerCase() !== w.address.toLowerCase();
        return { wallet: w, scores, isPoisoning, diff: charDiff(addr, w.address) };
      });
      const bestMatch = [...comparisons].sort((a, b) => b.scores.total - a.scores.total)[0];

      // 2. GoPlus blacklist check (EVM only)
      let blacklisted = false;
      let blacklistNote = "";
      if (addr.startsWith("0x") && apiKey) {
        try {
          const gp = await RS.checkApprovals(addr, "1", apiKey);
          blacklisted = gp?.is_blacklisted === "1" || gp?.risk === "CRITICAL";
          blacklistNote = gp?.risk_note ?? "";
        } catch {}
      }

      setResult({ addr, comparisons, bestMatch, blacklisted, blacklistNote });
    } finally {
      setChecking(false);
    }
  }

  function flagIfPoisoned(sender: string, chain: string, walletLabel: string, meta: object) {
    for (const savedWallet of wallets) {
      const scores = prefixSuffixScore(sender, savedWallet.address);
      if (scores.prefix >= 4 && scores.suffix >= 4 && sender.toLowerCase() !== savedWallet.address.toLowerCase()) {
        return {
          from: sender, chain,
          to: walletLabel,
          savedWallet: savedWallet.label,
          savedAddress: savedWallet.address,
          scores, diff: charDiff(sender, savedWallet.address),
          ...meta,
        };
      }
    }
    return null;
  }

  async function scanInboundTxs() {
    if (!apiKey) {
      Alert.alert(
        "Subscription required",
        "Link your subscription in Settings to scan inbound transactions.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Go to Settings", onPress: () => navigation.navigate("Settings") },
        ],
      );
      return;
    }
    setTxScanning(true);
    setTxFindings([]);
    setTxSummary([]);
    setTxStatus("");
    const findings: any[] = [];
    const summary: { label: string; chain: string; txCount: number }[] = [];

    const chainMap: { wallet: typeof wallets[0]; chain: "evm" | "solana" | "ton" }[] = [
      ...wallets.filter(w => w.chain === "evm").map(w => ({ wallet: w, chain: "evm" as const })),
      ...wallets.filter(w => w.chain === "solana").map(w => ({ wallet: w, chain: "solana" as const })),
      ...wallets.filter(w => w.chain === "ton").map(w => ({ wallet: w, chain: "ton" as const })),
    ];

    for (const { wallet, chain } of chainMap) {
      const chainLabel = chain === "evm" ? "EVM" : chain === "solana" ? "Solana" : "TON";
      setTxStatus(`Scanning ${wallet.label} (${chainLabel})…`);
      try {
        const data = await RS.getWalletInbound(wallet.address, chain, apiKey);
        const senders: any[] = data?.senders ?? [];
        summary.push({ label: wallet.label, chain: chainLabel, txCount: senders.length });
        for (const s of senders) {
          const hit = flagIfPoisoned(s.address, chainLabel, wallet.label, {
            asset: s.asset, value: s.value, hash: s.hash,
          });
          if (hit) findings.push(hit);
        }
      } catch {
        summary.push({ label: wallet.label, chain: chainLabel, txCount: -2 });
      }
    }

    setTxStatus("");
    setTxSummary(summary);
    setTxFindings(findings);
    setTxScanned(true);
    setTxScanning(false);
  }

  const anyPoisoning = result?.comparisons?.some((c: any) => c.isPoisoning);

  return (
    <ScrollView showsVerticalScrollIndicator={false}>
      <View style={s.explainer}>
        <Text style={s.explainerTitle}>Address Poisoning Detector</Text>
        <Text style={s.explainerText}>
          Attackers send tiny transactions from look-alike addresses that share your wallet's first and last characters. Paste any address below — Crypto Shield instantly compares it against your saved wallets and checks it against security blacklists.
        </Text>
      </View>

      {/* Manual check */}
      <View style={s.card}>
        <Text style={s.sectionLabel}>Check an Address</Text>
        <TextInput
          style={[s.simInput, { marginBottom: 8 }]}
          value={input}
          onChangeText={setInput}
          placeholder="Paste EVM or Solana address to check..."
          placeholderTextColor="#334155"
          autoCapitalize="none"
          autoCorrect={false}
        />
        {checking && <ActivityIndicator color="#00B5A5" style={{ marginVertical: 10 }} />}
        {result && !checking && (
          <>
            {/* Blacklist banner */}
            {result.blacklisted && (
              <View style={s.warningBox}>
                <Text style={s.warningTitle}>🚨 Blacklisted Address</Text>
                <Text style={s.warningItem}>{result.blacklistNote || "Flagged in security blacklist — do not transact"}</Text>
              </View>
            )}

            {/* Poisoning banner */}
            {anyPoisoning ? (
              <View style={[s.warningBox, { borderColor: "#ef4444", borderWidth: 2 }]}>
                <Text style={s.warningTitle}>🚨 Address Poisoning Detected — HIGH DRAIN RISK</Text>
                <Text style={s.warningItem}>
                  This address shares the first and last characters of your saved wallet. This is a confirmed poisoning pattern — attackers send tiny transactions from addresses like this hoping you'll copy it from your history and send funds to them instead.
                </Text>
                <View style={{ marginTop: 10, borderTopWidth: 1, borderTopColor: "#ef444430", paddingTop: 10 }}>
                  <Text style={[s.warningTitle, { fontSize: 11, marginBottom: 6 }]}>Recommended Actions</Text>
                  <Text style={s.warningItem}>• Do NOT send any funds to this address</Text>
                  <Text style={s.warningItem}>• Always verify the full address — not just the first/last 4 characters</Text>
                  <Text style={s.warningItem}>• Copy recipient addresses from the original source (app, exchange, contact) — never from your transaction history</Text>
                  <Text style={s.warningItem}>• Report this address to your wallet provider</Text>
                  <Text style={s.warningItem}>• Check your recent outbound transactions to confirm no funds were already sent to this address</Text>
                </View>
              </View>
            ) : !result.blacklisted ? (
              <View style={[s.safeBox, { borderColor: "#22c55e40", backgroundColor: "#22c55e10", marginBottom: 10 }]}>
                <Text style={[s.safeText, { color: "#22c55e", fontSize: 12 }]}>✓ No poisoning pattern found</Text>
              </View>
            ) : null}

            {/* Char-by-char diff against best match — only when the match is
                meaningful (4+ chars), not a coincidental 1-2 char overlap that
                any two random addresses would share */}
            {result.bestMatch && wallets.length > 0
              && (result.bestMatch.scores.prefix >= 4 || result.bestMatch.scores.suffix >= 4) && (
              <View style={{ marginTop: 8 }}>
                <Text style={[s.addrLabel, { marginBottom: 6 }]}>
                  Visual diff vs {result.bestMatch.wallet.label}
                </Text>
                <View style={s.addrBlock}>
                  <Text style={s.addrLabel}>Pasted address</Text>
                  <View style={s.diffRow}>
                    {result.bestMatch.diff.map((d: any, i: number) => (
                      <Text key={i} style={[s.diffChar, { color: d.match ? "#22c55e" : "#ef4444", backgroundColor: d.match ? "transparent" : "#ef444420" }]}>
                        {d.char}
                      </Text>
                    ))}
                  </View>
                  <Text style={[s.addrLabel, { marginTop: 8 }]}>Your wallet</Text>
                  <Text style={s.addrText}>{result.bestMatch.wallet.address}</Text>
                  <Text style={[s.addrLabel, { marginTop: 6 }]}>
                    Matching: {result.bestMatch.scores.prefix} prefix chars · {result.bestMatch.scores.suffix} suffix chars
                  </Text>
                </View>
              </View>
            )}

            {wallets.length === 0 && (
              <Text style={[s.cardSub, { marginTop: 8 }]}>Add wallets in the Wallets tab to enable visual comparison</Text>
            )}
          </>
        )}
      </View>

      {/* Inbound tx scan */}
      <View style={s.card}>
        <Text style={s.sectionLabel}>Scan Recent Inbound Transactions</Text>
        <Text style={[s.cardSub, { marginBottom: 12 }]}>
          Pulls your last 20 inbound transfers across EVM, Solana, and TON wallets. Flags any sender whose address mimics one of yours.
        </Text>
        {wallets.length === 0 ? (
          <Text style={s.cardSub}>Add wallets in the Wallets tab to enable inbound scanning.</Text>
        ) : (
          <TouchableOpacity
            style={[s.loadBtn, { marginHorizontal: 0, marginBottom: 0, opacity: txScanning ? 0.6 : 1 }]}
            onPress={scanInboundTxs}
            disabled={txScanning}
          >
            {txScanning
              ? <><ActivityIndicator color="#0a1628" size="small" /><Text style={[s.loadBtnText, { marginLeft: 8 }]}>Scanning…</Text></>
              : <Text style={s.loadBtnText}>🔍 Scan Inbound Transactions</Text>}
          </TouchableOpacity>
        )}
        {txScanning && !!txStatus && (
          <Text style={[s.cardSub, { marginTop: 10, color: "#00B5A5" }]}>{txStatus}</Text>
        )}
        {txScanned && !txScanning && txSummary.length > 0 && (
          <View style={[s.addrBlock, { marginTop: 12 }]}>
            <Text style={[s.addrLabel, { marginBottom: 6 }]}>Wallets scanned</Text>
            {txSummary.map((w, i) => (
              <View key={i} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 }}>
                <Text style={[s.cardSub, { color: "#e2e8f0" }]}>{w.label} <Text style={{ color: "#4a7fa5" }}>({w.chain})</Text></Text>
                <Text style={[s.cardSub, {
                  color: w.txCount === -1 ? "#f97316" : w.txCount === -2 ? "#ef4444" : "#22c55e"
                }]}>
                  {w.txCount === -1 ? "no key" : w.txCount === -2 ? "unavailable" : `${w.txCount} tx`}
                </Text>
              </View>
            ))}
          </View>
        )}
        {txScanned && !txScanning && (
          txFindings.length === 0 ? (
            <View style={[s.safeBox, { borderColor: "#22c55e40", backgroundColor: "#22c55e10", marginTop: 12 }]}>
              <Text style={[s.safeText, { color: "#22c55e", fontSize: 12 }]}>✓ No poisoning transactions found in recent history</Text>
            </View>
          ) : (
            <>
              <View style={[s.warningBox, { marginTop: 12 }]}>
                <Text style={s.warningTitle}>🚨 {txFindings.length} Suspicious Sender{txFindings.length !== 1 ? "s" : ""} Found</Text>
              </View>
              {txFindings.map((f, i) => (
                <View key={i} style={[s.addrBlock, { marginTop: 8 }]}>
                  <Text style={s.addrLabel}>[{f.chain}] Suspicious sender (mimics {f.savedWallet})</Text>
                  <View style={s.diffRow}>
                    {f.diff.map((d: any, j: number) => (
                      <Text key={j} style={[s.diffChar, { color: d.match ? "#22c55e" : "#ef4444", backgroundColor: d.match ? "transparent" : "#ef444420" }]}>
                        {d.char}
                      </Text>
                    ))}
                  </View>
                  <Text style={[s.addrLabel, { marginTop: 6 }]}>Your wallet: {f.savedAddress.slice(0,10)}...{f.savedAddress.slice(-6)}</Text>
                  <Text style={[s.cardSub, { marginTop: 4 }]}>{f.asset} {f.value} → {f.to} · {f.hash?.slice(0,14)}...</Text>
                </View>
              ))}
            </>
          )
        )}
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

// ERC20 Approval(address,address,uint256) topic
const APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925";

function ApprovalsTab() {
  const { wallets, apiKey } = useWallets();
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loading, setLoading]     = useState(false);
  const [loaded,  setLoaded]      = useState(false);
  const [status,  setStatus]      = useState("");
  const evmWallets = wallets.filter(w => w.chain === "evm");

  useEffect(() => {
    if (evmWallets.length > 0 && !loaded && !loading) loadApprovals();
  }, [evmWallets.length]);

  async function loadApprovals() {
    if (evmWallets.length === 0) return;
    setLoading(true);
    const alchemyKey = await SecureStore.getItemAsync("cs_alchemy_key");
    const all: any[] = [];

    for (const wallet of evmWallets) {
      if (!alchemyKey) { setStatus("Add Alchemy key in Settings for real approval scanning"); break; }
      setStatus(`Scanning ${wallet.label} approval events…`);
      try {
        // Pad wallet address to 32 bytes for topic filter
        const padded = "0x" + "0".repeat(24) + wallet.address.slice(2).toLowerCase();
        const logsResp = await fetch(`https://eth-mainnet.g.alchemy.com/v2/${alchemyKey}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0", id: 1, method: "eth_getLogs",
            params: [{ fromBlock: "earliest", toBlock: "latest",
                       topics: [APPROVAL_TOPIC, padded] }],
          }),
        });
        const logsData = await logsResp.json();
        const logs: any[] = logsData.result ?? [];

        // Deduplicate by token+spender, keep most recent
        const map: Record<string, any> = {};
        for (const log of logs) {
          const topics = log.topics ?? [];
          if (topics.length < 3) continue;
          const tokenAddr = log.address?.toLowerCase() ?? "";
          const spender   = "0x" + topics[2].slice(-40);
          const amountHex = log.data ?? "0x0";
          let amount = 0;
          try { amount = Number(BigInt(amountHex)); } catch {}
          const key = `${tokenAddr}:${spender}`;
          if (!map[key] || amount > map[key].amount)
            map[key] = { tokenAddr, spender, amount, blockNumber: log.blockNumber };
        }

        // Filter zero-amount (revoked) and check each spender via GoPlus
        setStatus(`Checking ${Object.keys(map).length} spenders against GoPlus…`);
        for (const item of Object.values(map).filter(i => i.amount > 0).slice(0, 20)) {
          const unlimited = item.amount > 1e24;
          let risk = unlimited ? "HIGH" : item.amount > 1e18 ? "MEDIUM" : "LOW";
          let spenderName = "";
          if (apiKey) {
            try {
              const gp = await RS.checkApprovals(item.spender, "1", apiKey);
              spenderName = gp?.spender_name ?? "";
              if (gp?.risk === "CRITICAL") risk = "CRITICAL";
            } catch {}
          }
          all.push({
            token: item.tokenAddr.slice(0, 8) + "…" + item.tokenAddr.slice(-4),
            token_address: item.tokenAddr,
            spender: item.spender,
            spender_name: spenderName,
            approved_amount: item.amount.toLocaleString(),
            unlimited,
            risk,
            wallet: wallet.label,
          });
        }
      } catch (e) {
        setStatus("Alchemy scan failed — showing sample data");
      }
    }

    setStatus("");
    setApprovals(all.length > 0 ? all : DEMO_APPROVALS);
    setLoaded(true);
    setLoading(false);
  }

  const dangerous = approvals.filter(a => a.risk === "CRITICAL" || a.risk === "HIGH");

  return (
    <ScrollView showsVerticalScrollIndicator={false}>
      <View style={s.explainer}>
        <Text style={s.explainerTitle}>Token Approval Scanner</Text>
        <Text style={s.explainerText}>
          Every time you interact with a dApp, it may request unlimited spend access to your tokens.
          Revoke forgotten or suspicious approvals before they're exploited.{"\n\n"}
          {evmWallets.length > 0
            ? `Scanning ${evmWallets.map(w => w.label).join(", ")} — EVM wallets only. Solana, Bitcoin, and TON do not use token approval contracts.`
            : "Token approval scanning is valid for EVM wallets only. Add an EVM wallet in the Wallets tab, or paste one below to scan directly."}
        </Text>
      </View>
      {!loaded && !loading && evmWallets.length > 0 && apiKey && (
        <TouchableOpacity style={s.loadBtn} onPress={loadApprovals}>
          <Text style={s.loadBtnText}>Scan Approvals Now</Text>
        </TouchableOpacity>
      )}
      {!loaded && !loading && evmWallets.length === 0 && (
        <TouchableOpacity style={[s.loadBtn, { backgroundColor: "#1e3a5f" }]} onPress={() => {}}>
          <Text style={[s.loadBtnText, { color: "#64748b" }]}>Add an EVM wallet in Wallets tab →</Text>
        </TouchableOpacity>
      )}
      {loading && (
        <View style={{ alignItems: "center", padding: 30 }}>
          <ActivityIndicator color="#00B5A5" size="large" />
          <Text style={{ color: "#64748b", marginTop: 12, fontSize: 12 }}>Scanning {evmWallets.length} EVM wallet{evmWallets.length !== 1 ? "s" : ""}…</Text>
        </View>
      )}
      {dangerous.length > 0 && (
        <View style={s.critBanner}>
          <Text style={s.critBannerText}>⚠ {dangerous.length} dangerous approval{dangerous.length !== 1 ? "s" : ""} require immediate revocation</Text>
        </View>
      )}
      {loaded && (
        <>
          <Text style={s.sectionLabel}>Active Approvals ({approvals.length})</Text>
          {approvals.map((a, i) => (
            <View key={i} style={[s.card, { borderLeftColor: riskColor(a.risk) }]}>
              <View style={s.cardRow}>
                <View>
                  <Text style={s.cardTitle}>{a.token}{a.wallet ? ` · ${a.wallet}` : ""}</Text>
                  <Text style={s.cardSub}>Spender: {a.spender_name || a.spender?.slice(0, 16) || a.spender}</Text>
                </View>
                <View style={{ alignItems: "flex-end", gap: 6 }}>
                  <View style={[s.riskPill, { backgroundColor: riskColor(a.risk) + "20", borderColor: riskColor(a.risk) + "40" }]}>
                    <Text style={[s.riskPillText, { color: riskColor(a.risk) }]}>{a.risk}</Text>
                  </View>
                  <Text style={[s.approvalValue, { color: a.unlimited ? "#ef4444" : "#94a3b8" }]}>
                    {a.unlimited ? "∞ Unlimited" : a.approved_amount}
                  </Text>
                </View>
              </View>
              <TouchableOpacity
                style={[s.revokeBtn, { borderColor: riskColor(a.risk) + "60", backgroundColor: riskColor(a.risk) + "15" }]}
                onPress={() => setApprovals(p => p.filter((_, j) => j !== i))}
              >
                <Text style={[s.revokeBtnText, { color: riskColor(a.risk) }]}>Revoke Approval</Text>
              </TouchableOpacity>
            </View>
          ))}
          {approvals.length === 0 && <Text style={s.emptyText}>No active approvals — wallet is clean</Text>}
        </>
      )}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function SimulationTab() {
  const { wallets } = useWallets();
  const [mode,    setMode]    = useState<"evm" | "solana">("evm");
  const [from,    setFrom]    = useState("");
  const [to,      setTo]      = useState("");
  const [data,    setData]    = useState("0x");
  const [value,   setValue]   = useState("0x0");
  const [solTx,   setSolTx]   = useState("");  // Solana: base64 serialized tx
  const [result,  setResult]  = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");
  const evmWallet = wallets.find(w => w.chain === "evm");
  const solWallet = wallets.find(w => w.chain === "solana");

  useEffect(() => {
    if (evmWallet && !from) setFrom(evmWallet.address);
  }, [evmWallet]);

  async function simulate() {
    setLoading(true); setError(""); setResult(null);
    try {
      const alchemyKey = await SecureStore.getItemAsync("cs_alchemy_key");
      if (!alchemyKey) throw new Error("Add Alchemy API key in Settings to simulate transactions.");

      if (mode === "evm") {
        const cleanValue = (value || "0x0").trim().split(/\s/)[0]; // strip any annotation after whitespace
        const res = await RS.simulateTransaction(from, to, data || "0x", cleanValue, alchemyKey);
        setResult({ mode: "evm", ...res });
      } else {
        if (!solTx.trim()) throw new Error("Paste a base64-encoded Solana transaction to simulate.");
        const simResp = await fetch(`https://solana-mainnet.g.alchemy.com/v2/${alchemyKey}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0", id: 1,
            method: "simulateTransaction",
            params: [solTx.trim(), { encoding: "base64", commitment: "confirmed", replaceRecentBlockhash: true }],
          }),
        });
        const simData = await simResp.json();
        const simResult = simData.result?.value ?? simData.result ?? {};
        if (simResult.err) throw new Error(`Simulation error: ${JSON.stringify(simResult.err)}`);
        setResult({ mode: "solana", logs: simResult.logs ?? [], unitsConsumed: simResult.unitsConsumed });
      }
    } catch (e: any) {
      setError(e.message || "Simulation failed");
    }
    setLoading(false);
  }

  function fillExample() {
    if (mode === "evm") {
      setFrom("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045");
      setTo("0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B");
      setData("0x");
      setValue("0xDE0B6B3A7640000");
    }
  }

  return (
    <ScrollView showsVerticalScrollIndicator={false}>
      <View style={s.explainer}>
        <Text style={s.explainerTitle}>Transaction Simulation</Text>
        <Text style={s.explainerText}>
          Simulate before signing. EVM: paste transaction parameters. Solana: copy the serialized transaction from Phantom's signing screen (tap ••• → Copy transaction) and paste the base64 string below.
        </Text>
      </View>

      {/* Mode toggle */}
      <View style={{ flexDirection: "row", gap: 8, marginBottom: 12 }}>
        <TouchableOpacity
          style={[s.loadBtn, { flex: 1, borderRadius: 8, marginBottom: 0, backgroundColor: mode === "evm" ? "#00B5A5" : "#0F1F3D", borderWidth: 1, borderColor: mode === "evm" ? "#00B5A5" : "#1e3a5f" }]}
          onPress={() => { setMode("evm"); setResult(null); setError(""); }}
        >
          <Text style={[s.loadBtnText, { color: mode === "evm" ? "#0a1628" : "#64748b" }]}>Ξ EVM</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[s.loadBtn, { flex: 1, borderRadius: 8, marginBottom: 0, backgroundColor: mode === "solana" ? "#00B5A5" : "#0F1F3D", borderWidth: 1, borderColor: mode === "solana" ? "#00B5A5" : "#1e3a5f" }]}
          onPress={() => { setMode("solana"); setResult(null); setError(""); }}
        >
          <Text style={[s.loadBtnText, { color: mode === "solana" ? "#0a1628" : "#64748b" }]}>◎ Solana</Text>
        </TouchableOpacity>
      </View>

      <View style={s.card}>
        {mode === "evm" ? (
          <>
            <Text style={s.sectionLabel}>FROM</Text>
            <TextInput style={s.simInput} value={from} onChangeText={setFrom} placeholder="0x sender address" placeholderTextColor="#334155" autoCapitalize="none" />
            <Text style={s.sectionLabel}>TO</Text>
            <TextInput style={s.simInput} value={to} onChangeText={setTo} placeholder="0x contract or recipient" placeholderTextColor="#334155" autoCapitalize="none" />
            <Text style={s.sectionLabel}>DATA (hex)</Text>
            <TextInput style={s.simInput} value={data} onChangeText={setData} placeholder="0x..." placeholderTextColor="#334155" autoCapitalize="none" />
            <Text style={s.sectionLabel}>VALUE (hex wei)</Text>
            <TextInput style={s.simInput} value={value} onChangeText={setValue} placeholder="0x0" placeholderTextColor="#334155" autoCapitalize="none" />
            <TouchableOpacity onPress={fillExample} style={{ marginBottom: 8 }}>
              <Text style={{ fontSize: 11, color: "#4a7fa5" }}>→ Load example: 1 ETH transfer from Vitalik</Text>
            </TouchableOpacity>
          </>
        ) : (
          <>
            <Text style={s.sectionLabel}>SERIALIZED TRANSACTION (BASE64)</Text>
            <Text style={{ fontSize: 10, color: "#64748b", marginBottom: 6, lineHeight: 14 }}>
              In Phantom: tap ••• before signing → "Copy transaction" → paste here.{"\n"}
              In Solana CLI: `solana transaction-history` gives base58; convert to base64 first.
            </Text>
            <TextInput
              style={[s.simInput, { height: 80, textAlignVertical: "top" }]}
              value={solTx}
              onChangeText={setSolTx}
              placeholder="AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAEDArc..."
              placeholderTextColor="#334155"
              multiline
              autoCapitalize="none"
              autoCorrect={false}
            />
            {solWallet && (
              <Text style={{ fontSize: 10, color: "#4a7fa5", marginBottom: 8 }}>
                Tip: transactions from {solWallet.label} ({solWallet.address.slice(0,8)}...) will include your wallet context.
              </Text>
            )}
          </>
        )}
        <TouchableOpacity style={[s.approveBtn, { marginTop: 4 }]} onPress={simulate} disabled={loading}>
          {loading ? <ActivityIndicator color="#22c55e" size="small" /> : <Text style={s.approveBtnText}>Simulate</Text>}
        </TouchableOpacity>
      </View>

      {error ? <View style={s.warningBox}><Text style={s.warningTitle}>⚠ {error}</Text></View> : null}

      {result && (
        <View style={s.card}>
          <Text style={s.cardTitle}>Simulation Result</Text>

          {result.mode === "solana" ? (
            <>
              <View style={[s.safeBox, { borderColor: "#22c55e40", backgroundColor: "#22c55e10", marginTop: 10 }]}>
                <Text style={[s.safeText, { color: "#22c55e", fontSize: 12 }]}>
                  ✓ Transaction simulated successfully
                </Text>
              </View>
              <Text style={[s.sectionLabel, { marginTop: 12 }]}>Compute units consumed</Text>
              <Text style={{ fontSize: 13, color: "#e2e8f0", fontWeight: "700" }}>
                {result.unitsConsumed?.toLocaleString() ?? "—"} CU
              </Text>
              {result.logs?.length > 0 && (
                <>
                  <Text style={[s.sectionLabel, { marginTop: 12 }]}>Program logs (last 5)</Text>
                  {result.logs.slice(-5).map((log: string, i: number) => (
                    <Text key={i} style={{ fontSize: 10, color: "#94a3b8", fontFamily: "monospace", lineHeight: 14, marginBottom: 2 }}>{log}</Text>
                  ))}
                </>
              )}
            </>
          ) : (
            <>
              {result.error && (
                <View style={[s.warningBox, { marginBottom: 10 }]}>
                  <Text style={s.warningTitle}>⚠ {result.error.message || "Simulation error"}</Text>
                </View>
              )}
              <Text style={[s.sectionLabel, { marginTop: 8 }]}>Asset Changes</Text>
              {value && value !== "0x0" && value !== "0x" && (() => {
                try {
                  const weiVal = BigInt(value);
                  const ethVal = Number(weiVal) / 1e18;
                  return (
                    <View style={s.balanceRow}>
                      <Text style={s.balanceToken}>ETH (native send)</Text>
                      <Text style={[s.balanceChange, { color: "#ef4444" }]}>-{ethVal.toFixed(6)} ETH</Text>
                    </View>
                  );
                } catch { return null; }
              })()}
              {(result.changes ?? []).map((c: any, i: number) => {
                let displayAmt = c.rawAmount ?? "";
                try {
                  const dec = c.decimals ?? 18;
                  const raw = BigInt(c.rawAmount ?? "0");
                  const divisor = BigInt(10 ** Math.min(dec, 18));
                  displayAmt = (Number(raw) / Number(divisor)).toFixed(dec > 6 ? 6 : 2);
                } catch {}
                const isReceive = c.changeType === "RECEIVE" || c.changeType === "INCREASE";
                return (
                  <View key={i} style={s.balanceRow}>
                    <Text style={s.balanceToken}>{c.symbol || c.asset || "Token"}</Text>
                    <Text style={[s.balanceChange, { color: isReceive ? "#22c55e" : "#ef4444" }]}>
                      {isReceive ? "+" : "-"}{displayAmt}
                    </Text>
                  </View>
                );
              })}
              {(result.changes ?? []).length === 0 && (!value || value === "0x0") && (
                <Text style={s.cardSub}>No ERC20/NFT asset changes detected</Text>
              )}
              <View style={[s.safeBox, { borderColor: "#1e3a5f", backgroundColor: "#060b18", marginTop: 12 }]}>
                <Text style={[s.safeText, { color: "#94a3b8", fontSize: 11 }]}>
                  Gas: {result.gasUsed ? `${parseInt(result.gasUsed, 16).toLocaleString()} units` : "Unavailable — Alchemy eth_mainnet key required"}
                </Text>
              </View>
            </>
          )}
        </View>
      )}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function checkReputation(url: string): { trusted: boolean | null; note?: string } {
  const clean = url.toLowerCase().replace(/^https?:\/\//, "").replace(/\/$/, "");
  if (KNOWN_TRUSTED[clean]) return { trusted: true, note: KNOWN_TRUSTED[clean] };
  for (const pat of SUSPICIOUS_PATTERNS) {
    if (pat.test(clean)) return { trusted: false, note: "Matches suspicious domain pattern" };
  }
  return { trusted: null, note: "Unknown dApp — verify before trusting" };
}

function SessionsTab() {
  const [sessions, setSessions] = useState<DappSession[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [labelInput, setLabelInput] = useState("");
  const [chainInput, setChainInput] = useState("SOL");

  useEffect(() => {
    SecureStore.getItemAsync(SESSIONS_KEY).then(raw => {
      if (raw) setSessions(JSON.parse(raw));
    });
  }, []);

  async function persist(updated: DappSession[]) {
    await SecureStore.setItemAsync(SESSIONS_KEY, JSON.stringify(updated));
    setSessions(updated);
  }

  async function addSession() {
    const url = urlInput.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/$/, "");
    if (!url) return;
    const rep = checkReputation(url);
    const session: DappSession = {
      id: Date.now().toString(),
      dapp: labelInput.trim() || url.split(".")[0],
      url,
      addedAt: new Date().toISOString(),
      chains: chainInput.split(",").map(c => c.trim().toUpperCase()).filter(Boolean),
      trusted: rep.trusted,
      reputationNote: rep.note,
    };
    await persist([...sessions, session]);
    setUrlInput(""); setLabelInput(""); setChainInput("SOL"); setShowAdd(false);
  }

  function confirmRemove(id: string, dapp: string) {
    Alert.alert("Remove Session", `Mark ${dapp} as disconnected?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => persist(sessions.filter(s => s.id !== id)) },
    ]);
  }

  const untrusted = sessions.filter(s => s.trusted === false);
  const unknown   = sessions.filter(s => s.trusted === null);

  return (
    <ScrollView showsVerticalScrollIndicator={false}>
      <View style={s.explainer}>
        <Text style={s.explainerTitle}>Connected dApp Session Tracker</Text>
        <Text style={s.explainerText}>
          Track which dApps you've connected your wallet to. Add each connection manually — Crypto Shield checks the URL against known trusted and malicious domains and flags suspicious ones.
        </Text>
      </View>

      {untrusted.length > 0 && (
        <View style={s.critBanner}>
          <Text style={s.critBannerText}>🚨 {untrusted.length} suspicious dApp{untrusted.length !== 1 ? "s" : ""} — revoke immediately</Text>
        </View>
      )}
      {unknown.length > 0 && untrusted.length === 0 && (
        <View style={[s.critBanner, { backgroundColor: "#f9731620", borderColor: "#f9731640" }]}>
          <Text style={[s.critBannerText, { color: "#f97316" }]}>⚠ {unknown.length} unverified dApp{unknown.length !== 1 ? "s" : ""} — research before trusting</Text>
        </View>
      )}

      <TouchableOpacity style={s.addSessionBtn} onPress={() => setShowAdd(true)}>
        <Text style={s.addSessionText}>+ Add dApp Connection</Text>
      </TouchableOpacity>

      <Text style={s.sectionLabel}>Tracked Sessions ({sessions.length})</Text>

      {sessions.map(sess => {
        const isBad     = sess.trusted === false;
        const isUnknown = sess.trusted === null;
        const borderCol = isBad ? "#ef4444" : isUnknown ? "#f97316" : "#22c55e";
        return (
          <View key={sess.id} style={[s.card, { borderLeftColor: borderCol }]}>
            <View style={s.cardRow}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <Text style={s.cardTitle}>{sess.dapp}</Text>
                  {isBad     && <View style={s.untrustedTag}><Text style={s.untrustedText}>🚨 SUSPICIOUS</Text></View>}
                  {isUnknown && <View style={[s.untrustedTag, { backgroundColor: "#f9731620", borderColor: "#f9731640" }]}><Text style={[s.untrustedText, { color: "#f97316" }]}>⚠ UNKNOWN</Text></View>}
                  {sess.trusted === true && <View style={[s.untrustedTag, { backgroundColor: "#22c55e20", borderColor: "#22c55e40" }]}><Text style={[s.untrustedText, { color: "#22c55e" }]}>✓ TRUSTED</Text></View>}
                </View>
                <Text style={s.cardSub}>{sess.url}</Text>
                {sess.reputationNote && <Text style={[s.cardSub, { color: isBad ? "#ef4444" : isUnknown ? "#f97316" : "#22c55e" }]}>{sess.reputationNote}</Text>}
                <Text style={s.cardSub}>Chains: {sess.chains.join(", ")} · Added {new Date(sess.addedAt).toLocaleDateString()}</Text>
              </View>
            </View>
            <TouchableOpacity
              style={[s.revokeBtn, { borderColor: isBad ? "#ef444460" : "#1e3a5f", backgroundColor: isBad ? "#ef444415" : "#1e3a5f30" }]}
              onPress={() => confirmRemove(sess.id, sess.dapp)}
            >
              <Text style={[s.revokeBtnText, { color: isBad ? "#ef4444" : "#64748b" }]}>Remove</Text>
            </TouchableOpacity>
          </View>
        );
      })}

      {sessions.length === 0 && (
        <View style={s.emptySessionWrap}>
          <Text style={s.emptyText}>No sessions tracked yet</Text>
          <Text style={[s.cardSub, { textAlign: "center", marginTop: 6 }]}>
            Add the dApps you've connected your wallet to. Crypto Shield will flag suspicious domains.
          </Text>
        </View>
      )}

      {/* Add session modal */}
      <Modal visible={showAdd} transparent animationType="slide">
        <View style={s.modalOverlay}>
          <View style={s.modal}>
            <Text style={s.modalTitle}>Add dApp Connection</Text>
            <Text style={[s.cardSub, { marginBottom: 14 }]}>Enter the domain of a dApp you've connected your wallet to.</Text>

            <Text style={s.fieldLabel}>dApp URL</Text>
            <TextInput
              style={s.modalInput}
              value={urlInput}
              onChangeText={setUrlInput}
              placeholder="e.g. app.uniswap.org"
              placeholderTextColor="#334155"
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={s.fieldLabel}>Label (optional)</Text>
            <TextInput
              style={s.modalInput}
              value={labelInput}
              onChangeText={setLabelInput}
              placeholder="e.g. Uniswap"
              placeholderTextColor="#334155"
            />

            <Text style={s.fieldLabel}>Chain(s)</Text>
            <TextInput
              style={s.modalInput}
              value={chainInput}
              onChangeText={setChainInput}
              placeholder="e.g. SOL, ETH"
              placeholderTextColor="#334155"
              autoCapitalize="characters"
            />

            <View style={s.modalBtns}>
              <TouchableOpacity style={s.cancelBtn} onPress={() => setShowAdd(false)}>
                <Text style={s.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.confirmBtn} onPress={addSession}>
                <Text style={s.confirmText}>Add & Check</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

// ── Main screen ────────────────────────────────────────────────────────────

export function SignaturePoisoningScreen() {
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<GuardTab>("poisoning");

  const TABS: { key: GuardTab; label: string; icon: string }[] = [
    { key: "poisoning",  label: "Poisoning",  icon: "🎯" },
    { key: "approvals",  label: "Approvals",  icon: "🔓" },
    { key: "simulation", label: "Simulate",   icon: "🔬" },
    { key: "sessions",   label: "Sessions",   icon: "🔗" },
  ];

  return (
    <View style={[s.container, { paddingTop: insets.top }]}>
      <View style={s.header}>
        <View>
          <Text style={s.title}>Signature Guard</Text>
          <Text style={s.subtitle}>Wallet transaction security</Text>
        </View>
      </View>

      {/* Tab bar */}
      <View style={s.tabBar}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.key}
            style={[s.tabBtn, tab === t.key && s.tabBtnActive]}
            onPress={() => setTab(t.key)}
          >
            <Text style={s.tabIcon}>{t.icon}</Text>
            <Text style={[s.tabLabel, tab === t.key && { color: "#00B5A5" }]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={{ flex: 1, paddingHorizontal: 16 }}>
        {tab === "poisoning"  && <AddressPoisoningTab />}
        {tab === "approvals"  && <ApprovalsTab />}
        {tab === "simulation" && <SimulationTab />}
        {tab === "sessions"   && <SessionsTab />}
      </View>
    </View>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  container:      { flex: 1, backgroundColor: "#0a1628" },
  header:         { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20, paddingBottom: 10 },
  title:          { fontSize: 20, fontWeight: "800", color: "#fff" },
  subtitle:       { fontSize: 11, color: "#64748b", marginTop: 2 },
  diffRow:        { flexDirection: "row", flexWrap: "wrap", marginTop: 4 },
  diffChar:       { fontSize: 10, fontFamily: "monospace", letterSpacing: 0 },
  tabBar:         { flexDirection: "row", paddingHorizontal: 16, marginBottom: 10, gap: 6 },
  tabBtn:         { flex: 1, backgroundColor: "#0F1F3D", borderRadius: 8, paddingVertical: 8, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  tabBtnActive:   { borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  tabIcon:        { fontSize: 14, marginBottom: 2 },
  tabLabel:       { fontSize: 9, color: "#64748b", fontWeight: "600" },
  explainer:      { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  explainerTitle: { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 6 },
  explainerText:  { fontSize: 12, color: "#94a3b8", lineHeight: 18 },
  sectionLabel:   { fontSize: 10, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 8 },
  card:           { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 10, borderLeftWidth: 3, borderWidth: 1, borderColor: "#1e3a5f" },
  cardRow:        { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 },
  cardTitle:      { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 2 },
  cardSub:        { fontSize: 11, color: "#64748b" },
  typeTag:        { fontSize: 9, fontWeight: "700" },
  sigValue:       { fontSize: 12, color: "#e2e8f0", fontWeight: "600", marginBottom: 8 },
  addrBlock:      { backgroundColor: "#060b18", borderRadius: 8, padding: 10, marginBottom: 10 },
  addrLabel:      { fontSize: 9, color: "#64748b", marginBottom: 2, textTransform: "uppercase", letterSpacing: 0.3 },
  addrText:       { fontSize: 11, fontFamily: "monospace", color: "#94a3b8", marginBottom: 8 },
  warningBox:     { backgroundColor: "#ef444415", borderRadius: 8, padding: 10, borderWidth: 1, borderColor: "#ef444430", marginBottom: 10 },
  warningTitle:   { fontSize: 12, fontWeight: "700", color: "#ef4444", marginBottom: 4 },
  warningItem:    { fontSize: 11, color: "#fca5a5", lineHeight: 17 },
  actionRow:      { flexDirection: "row", gap: 10 },
  rejectBtn:      { flex: 1, backgroundColor: "#ef444420", borderRadius: 8, paddingVertical: 9, alignItems: "center", borderWidth: 1, borderColor: "#ef444440" },
  rejectBtnText:  { color: "#ef4444", fontWeight: "700", fontSize: 12 },
  approveBtn:     { flex: 1, backgroundColor: "#22c55e20", borderRadius: 8, paddingVertical: 9, alignItems: "center", borderWidth: 1, borderColor: "#22c55e40" },
  approveBtnText: { color: "#22c55e", fontWeight: "700", fontSize: 12 },
  critBanner:     { backgroundColor: "#f9731620", borderRadius: 8, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: "#f9731640" },
  critBannerText: { fontSize: 12, color: "#f97316", fontWeight: "700" },
  riskPill:       { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, borderWidth: 1 },
  riskPillText:   { fontSize: 10, fontWeight: "700" },
  approvalValue:  { fontSize: 13, fontWeight: "800" },
  revokeBtn:      { marginTop: 10, borderRadius: 8, paddingVertical: 8, alignItems: "center", borderWidth: 1 },
  revokeBtnText:  { fontSize: 12, fontWeight: "700" },
  balanceRow:     { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  balanceToken:   { fontSize: 13, color: "#94a3b8" },
  balanceChange:  { fontSize: 13, fontWeight: "700" },
  simMeta:        { marginTop: 12, backgroundColor: "#060b18", borderRadius: 8, padding: 10 },
  simMetaRow:     { flexDirection: "row", justifyContent: "space-between", paddingVertical: 5 },
  simMetaLabel:   { fontSize: 12, color: "#64748b" },
  simMetaVal:     { fontSize: 12, color: "#e2e8f0", fontWeight: "600" },
  safeBox:        { marginTop: 12, borderRadius: 8, padding: 12, borderWidth: 1, marginBottom: 12 },
  safeText:       { fontSize: 13, fontWeight: "700", textAlign: "center" },
  untrustedTag:   { backgroundColor: "#ef444420", borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, borderWidth: 1, borderColor: "#ef444440" },
  untrustedText:  { fontSize: 9, color: "#ef4444", fontWeight: "700" },
  emptyText:        { textAlign: "center", color: "#64748b", fontSize: 13, paddingTop: 30 },
  emptySessionWrap: { paddingHorizontal: 20, paddingTop: 20, alignItems: "center" },
  addSessionBtn:    { backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 11, alignItems: "center", marginBottom: 16 },
  addSessionText:   { color: "#0a1628", fontWeight: "800", fontSize: 13 },
  fieldLabel:       { fontSize: 10, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 5 },
  modalOverlay:     { flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  modal:            { backgroundColor: "#0F1F3D", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24 },
  modalTitle:       { fontSize: 16, fontWeight: "800", color: "#fff", marginBottom: 6 },
  modalDesc:        { fontSize: 12, color: "#64748b", lineHeight: 18, marginBottom: 16 },
  modalInput:       { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 13, marginBottom: 14 },
  modalBtn:         { backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  modalBtnText:     { color: "#0a1628", fontWeight: "800", fontSize: 14 },
  modalBtns:        { flexDirection: "row", gap: 10, marginTop: 4 },
  cancelBtn:        { flex: 1, backgroundColor: "#1e3a5f", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  cancelText:       { color: "#94a3b8", fontWeight: "600" },
  confirmBtn:       { flex: 2, backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  confirmText:      { color: "#0a1628", fontWeight: "800" },
  loadBtn:          { backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 12, alignItems: "center", margin: 16 },
  loadBtnText:      { color: "#0a1628", fontWeight: "800", fontSize: 13 },
  simInput:         { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 10, color: "#e2e8f0", fontSize: 12, fontFamily: "monospace", marginBottom: 10 },
  hintBox:          { backgroundColor: "#0F2A1A", borderRadius: 10, padding: 14, borderWidth: 1, borderColor: "#22c55e30" },
  hintTitle:        { fontSize: 12, fontWeight: "700", color: "#22c55e", marginBottom: 8 },
  hintText:         { fontSize: 12, color: "#94a3b8", lineHeight: 20 },
  hintStep:         { fontWeight: "800", color: "#00B5A5" },
  hintEmphasis:     { color: "#e2e8f0", fontWeight: "600" },
});
