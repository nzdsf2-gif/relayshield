import React, { useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import { RiskGauge } from "../components/RiskGauge";
import { AttackChain } from "../components/AttackChain";
import { Speedometer } from "../components/Speedometer";
import { useWallets } from "../hooks/useWallet";
import * as RS from "../api/relayshield";
import { FeedbackPrompt, notePositiveMoment } from "../components/FeedbackPrompt";

type ScanType = "domain" | "token" | "sol" | "infostealer" | "airdrop" | "dapp" | "nft" | "nftsecurity" | "ton" | "base" | "bnb" | "xrp";

async function withRetry<T>(fn: () => Promise<T>, retries = 1, delayMs = 3000): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    if (retries <= 0) throw err;
    await new Promise(r => setTimeout(r, delayMs));
    return withRetry(fn, retries - 1, delayMs);
  }
}

const DEMO_AIRDROP_SCAM = {
  contract_address: "0xdemo",
  chain_id: "1",
  risk_level: "CRITICAL",
  critical_flags: ["airdrop scam", "honeypot"],
  warning_flags: ["hidden owner", "mintable supply", "transfers can be paused"],
  token_name: "FreeETH Reward Token",
  token_symbol: "FREETH",
  holder_count: "48291",
  raw: {
    is_airdrop_scam: 1, fake_token: 1, is_honeypot: 1,
    cannot_sell_all: 1, hidden_owner: 1, is_mintable: 1,
    transfer_pausable: 1, slippage_modifiable: 0, selfdestruct: 0,
    can_take_back_ownership: 1, owner_change_balance: 0,
    buy_tax: 0, sell_tax: 99, is_open_source: 0, is_proxy: 0,
  },
};

const SCAN_TYPES: { key: ScanType; label: string; placeholder: string; icon: string }[] = [
  { key: "domain",      label: "Domain Risk",    placeholder: "e.g. acme-corp.com",            icon: "🌐" },
  { key: "token",       label: "EVM Token",      placeholder: "Contract address — e.g. 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (Base USDC)", icon: "🪙" },
  { key: "sol",         label: "SOL Token",      placeholder: "Solana token mint address — e.g. EPjFW...",                                             icon: "◎" },
  { key: "infostealer", label: "Email Check",    placeholder: "e.g. user@company.com",          icon: "🔍" },
  { key: "airdrop",     label: "Airdrop Check",  placeholder: "0x contract address (type 'demo' to preview scam)", icon: "🪂" },
  { key: "dapp",        label: "dApp Risk",      placeholder: "e.g. app.uniswap.org",                              icon: "🔗" },
  { key: "nft",         label: "NFT Floor",      placeholder: "Collection slug — e.g. boredapeyachtclub, mad_lads, pudgypenguins", icon: "🖼" },
  { key: "nftsecurity", label: "NFT Security",   placeholder: "EVM NFT contract address — e.g. 0xBC4CA0EDA7647A8AB7C2061C2E118A18A936F13D", icon: "🔒" },
  { key: "ton",         label: "TON Address",    placeholder: "TON wallet or token contract — e.g. EQA..., UQA...",  icon: "💎" },
  { key: "base",        label: "Base Token",     placeholder: "Base contract address — e.g. 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (USDC)", icon: "🔵" },
  { key: "bnb",         label: "BNB Token",      placeholder: "BSC contract address — e.g. 0x55d3...",               icon: "🟡" },
  { key: "xrp",         label: "XRP Address",    placeholder: "XRP Ledger address — e.g. rf1BiGeXwwQoi8Z2ueFYTEXSwuJYfV2Jpn", icon: "⚡" },
];

// Scan types available WITHOUT a linked subscription.
//
// Added 2026-08-01. Previously every scan was blocked behind an API key, which
// made the free tier's "1 monitored wallet" close to useless — you could watch a
// wallet but never check whether the token that just landed in it was a scam.
// The pricing page has always advertised "Manual risk scans" on Free, so this
// also closes a live mismatch between what is sold and what is delivered.
//
// The split is not arbitrary: these are exactly the contract/address-reputation
// endpoints that carry no personal data. The two omitted types (Domain Risk and
// Email Check) hit /v1/metered/* endpoints, which look up people rather than
// contracts and genuinely require a key server-side — so they stay behind the
// subscription and now say so instead of failing with a generic error.
const FREE_SCAN_TYPES: ReadonlySet<ScanType> = new Set<ScanType>([
  "token", "sol", "airdrop", "dapp", "nft", "nftsecurity",
  "ton", "base", "bnb", "xrp",
]);

function isFreeScan(t: ScanType): boolean {
  return FREE_SCAN_TYPES.has(t);
}

// Chain options for EVM token/airdrop scanning
const EVM_CHAINS: { id: string; label: string }[] = [
  { id: "1",     label: "ETH" },
  { id: "56",    label: "BSC" },
  { id: "137",   label: "Polygon" },
  { id: "8453",  label: "Base" },
  { id: "43114", label: "Avalanche" },
  { id: "42161", label: "Arbitrum" },
  { id: "10",    label: "Optimism" },
  { id: "100",   label: "Gnosis" },
  { id: "999",   label: "Hyperliquid" },
];

export function ScanScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const { apiKey } = useWallets();
  const [scanType, setScanType] = useState<ScanType>("domain");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [selectedChain, setSelectedChain] = useState("1"); // default Ethereum
  const [showFeedback, setShowFeedback] = useState(false);

  const current = SCAN_TYPES.find(s => s.key === scanType)!;
  const showChainPicker = (scanType === "token" || scanType === "airdrop" || scanType === "nftsecurity");

  function resolveChainId(address: string): string {
    // Solana base58 — always "solana" regardless of picker
    if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address.trim()) &&
        !/^0x/.test(address.trim())) return "solana";
    // EVM — use whatever the user picked
    return selectedChain;
  }

  function validateInput(raw: string): string | null {
    const v = raw.trim();
    if (!v) return "Enter a value to scan.";
    if (scanType === "token" || scanType === "airdrop") {
      const isEVM    = /^0x[0-9a-fA-F]{40}$/.test(v);
      const isSolana = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(v) && !v.startsWith("0x");
      if (!isEVM && !isSolana && v.toLowerCase() !== "demo" && v.toLowerCase() !== "0xdemo") {
        return `Enter a contract address, not a token name.\nEVM: starts with 0x (42 chars) · Solana: base58 string (32–44 chars)\nExample Base USDC: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`;
      }
    }
    if (scanType === "nftsecurity" && !/^0x[0-9a-fA-F]{40}$/.test(v)) {
      return "Enter a valid EVM contract address — starts with 0x (42 chars). NFT Security only supports EVM chains.";
    }
    return null;
  }

  async function runScan() {
    if (!input.trim()) return;
    if (!apiKey && !isFreeScan(scanType)) {
      const t = SCAN_TYPES.find(s => s.key === scanType);
      setError(`${t?.label ?? "This scan"} needs a subscription — link yours in Settings. Token, NFT, airdrop and dApp scans are free.`);
      return;
    }
    const validationErr = validateInput(input);
    if (validationErr) { setError(validationErr); return; }
    setLoading(true); setResult(null); setError("");
    try {
      const addr = input.trim();
      const chainId = resolveChainId(addr);
      const data = await withRetry(async () => {
        let d: any;
        if (scanType === "domain")      d = await RS.getIdentityRisk(addr, apiKey);
        if (scanType === "infostealer") d = await RS.checkInfostealer(addr, apiKey);
        if (scanType === "token")       d = await RS.checkTokenRisk(addr, chainId, apiKey);
        if (scanType === "airdrop") {
          if (addr.toLowerCase() === "0xdemo" || addr.toLowerCase() === "demo") {
            d = DEMO_AIRDROP_SCAM;
          } else {
            d = await RS.checkTokenRisk(addr, chainId, apiKey);
            if (d && d.raw && d.raw.is_airdrop_scam == null) {
              d._airdrop_note = "Live data — airdrop_scam field requires active on-chain token";
            }
          }
        }
        if (scanType === "sol")  d = await RS.checkSolanaTokenRisk(addr, apiKey);
        if (scanType === "dapp") d = await RS.checkDappReputation(addr, apiKey);
        if (scanType === "nft")  d = await RS.checkNFTFloor(addr, apiKey);
        if (scanType === "nftsecurity") d = await RS.checkNFTSecurity(addr, chainId, apiKey);
        if (scanType === "ton")  d = await RS.checkTONAddress(addr, apiKey);
        if (scanType === "base") d = await RS.checkBaseToken(addr, apiKey!);
        if (scanType === "bnb")  d = await RS.checkBNBToken(addr, apiKey!);
        if (scanType === "xrp")  d = await RS.checkXRPAddress(addr, apiKey);
        return d;
      });
      setResult({ type: scanType, data, chainId });
      // Positive moment for feedback prompting — a completed scan that isn't
      // flagging something scary. Skip when risk_level exists and is bad,
      // since asking "enjoying the app?" right after a critical finding is tone-deaf.
      const riskLevel = (data?.risk_level || "").toUpperCase();
      if (riskLevel !== "CRITICAL" && riskLevel !== "HIGH") {
        notePositiveMoment().then(shouldAsk => { if (shouldAsk) setShowFeedback(true); });
      }
    } catch (e: any) {
      setError(e.message || "Scan failed — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={[styles.container, { paddingTop: insets.top }]}>
        <Text style={styles.title}>Scan</Text>
        <Text style={styles.subtitle}>Run a live threat intelligence check across wallets, tokens, NFTs, domains, and more</Text>

        {/* Scan type selector */}
        <View style={styles.typeRow}>
          {SCAN_TYPES.map(t => (
            <TouchableOpacity
              key={t.key}
              style={[styles.typeBtn, scanType === t.key && styles.typeBtnActive]}
              onPress={() => { setScanType(t.key); setResult(null); setInput(""); setError(""); }}
            >
              <Text style={styles.typeIcon}>{t.icon}</Text>
              <Text style={[styles.typeLabel, scanType === t.key && { color: "#00B5A5" }]}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Chain selector — shown only for token/airdrop scans */}
        {showChainPicker && (
          <View style={styles.chainRow}>
            {EVM_CHAINS.map(c => (
              <TouchableOpacity
                key={c.id}
                style={[styles.chainPill, selectedChain === c.id && styles.chainPillActive]}
                onPress={() => setSelectedChain(c.id)}
              >
                <Text style={[styles.chainPillText, selectedChain === c.id && { color: "#00B5A5" }]}>
                  {c.label}
                </Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity
              style={[styles.chainPill, selectedChain === "solana" && styles.chainPillActive]}
              onPress={() => setSelectedChain("solana")}
            >
              <Text style={[styles.chainPillText, selectedChain === "solana" && { color: "#00B5A5" }]}>SOL</Text>
            </TouchableOpacity>
          </View>
        )}

        <ScrollView showsVerticalScrollIndicator={false} style={{ flex: 1, paddingHorizontal: 16 }}>
          <View style={styles.inputCard}>
            <TextInput
              style={styles.input}
              value={input}
              onChangeText={setInput}
              placeholder={current.placeholder}
              placeholderTextColor="#4a7fa5"
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={runScan}
            />
            <TouchableOpacity
              style={[styles.scanBtn, loading && { opacity: 0.6 }]}
              onPress={runScan}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#0a1628" size="small" />
                : <Text style={styles.scanBtnText}>Scan Now</Text>
              }
            </TouchableOpacity>
          </View>

          {error ? (
            <View style={styles.errorCard}>
              <Text style={styles.errorText}>⚠ {error}</Text>
              {error.includes("subscription") && (
                <TouchableOpacity
                  style={{ marginTop: 8 }}
                  onPress={() => navigation.navigate("Settings")}
                >
                  <Text style={{ color: "#38bdf8", fontWeight: "600" }}>Go to Settings →</Text>
                </TouchableOpacity>
              )}
            </View>
          ) : null}

          {result && <ScanResult result={result} />}

          {/* Free-tier guidance when no subscription is linked */}
          {!apiKey && !result && !loading && (
            <View style={styles.demoNote}>
              <Text style={styles.demoNoteText}>
                {isFreeScan(scanType)
                  ? "✅ This scan is free — no subscription needed. Paste a contract or address above and tap Scan."
                  : "🔒 This scan needs a subscription — link yours in Settings.\n\nFree without one: EVM/SOL/Base/BNB tokens, TON and XRP addresses, airdrop, NFT and dApp checks."}
              </Text>
            </View>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      </View>
      <FeedbackPrompt visible={showFeedback} onDone={() => setShowFeedback(false)} />
    </KeyboardAvoidingView>
  );
}

function riskColor(level: string): string {
  const l = (level ?? "").toUpperCase();
  if (l === "CRITICAL") return "#ef4444";
  if (l === "HIGH")     return "#f97316";
  if (l === "MEDIUM")   return "#facc15";
  return "#22c55e";
}

function ScanResult({ result }: { result: any }) {
  const { type, data } = result;

  if (type === "domain") {
    const score  = data.risk_score ?? 0;
    const level  = data.risk_level ?? "LOW";
    const dims   = data.dimension_scores ?? {};
    const factors = data.risk_factors ?? [];
    return (
      <View style={styles.resultCard}>
        <View style={styles.resultHeader}>
          <RiskGauge score={score} size={100} />
          <View style={{ flex: 1, paddingLeft: 16 }}>
            <Text style={styles.resultTitle}>Identity Risk Score</Text>
            <Text style={styles.resultSummary}>{data.summary || ""}</Text>
          </View>
        </View>
        <Text style={styles.sectionLabel}>Signal Dimensions</Text>
        {Object.entries(dims).map(([k, v]: any) => (
          <DimBar key={k} label={k.replace(/_/g," ").replace(/\b\w/g,(c:string)=>c.toUpperCase()).replace(/\bIoc\b/g,"IOC").replace(/\bCve\b/g,"CVE")} value={v} max={25} />
        ))}
        {factors.length > 0 && <>
          <Text style={styles.sectionLabel}>Risk Factors</Text>
          {factors.map((f: string, i: number) => (
            <Text key={i} style={styles.factor}>• {f}</Text>
          ))}
        </>}
        <AttackChain dims={dims} score={score} />
      </View>
    );
  }

  if (type === "infostealer") {
    const found = data.found ?? false;
    const hits  = data.hits ?? 0;
    return (
      <View style={styles.resultCard}>
        <View style={[styles.infoBanner, { borderColor: found ? "#ef4444" : "#22c55e" }]}>
          <Text style={{ fontSize: 28 }}>{found ? "🚨" : "✅"}</Text>
          <View style={{ flex: 1, paddingLeft: 12 }}>
            <Text style={[styles.infoTitle, { color: found ? "#ef4444" : "#22c55e" }]}>
              {found ? `${hits} Infostealer Hit${hits !== 1 ? "s" : ""} Found` : "No Infostealer Exposure"}
            </Text>
            <Text style={styles.infoSub}>
              {found
                ? "Credentials found in criminal stealer archives. Rotate passwords immediately."
                : "Email not found in monitored stealer log corpus."}
            </Text>
          </View>
        </View>
      </View>
    );
  }

  // Token security result
  if (type === "token") {
    const level    = (data.risk_level || "LOW").toUpperCase() as "LOW"|"MEDIUM"|"HIGH"|"CRITICAL";
    const critical = data.critical_flags || [];
    const warnings = data.warning_flags  || [];
    const levelColor = level === "CRITICAL" ? "#ef4444" : level === "HIGH" ? "#f97316" : level === "MEDIUM" ? "#facc15" : "#22c55e";
    return (
      <View style={styles.resultCard}>
        {/* Token identity */}
        <View style={styles.tokenHeader}>
          <View>
            <Text style={styles.tokenName}>{data.token_name || "Unknown Token"}</Text>
            <Text style={styles.tokenSymbol}>{data.token_symbol || ""}</Text>
            <Text style={styles.tokenMeta}>
              {data.holder_count ? `${parseInt(data.holder_count).toLocaleString()} holders` : ""}
              {data.chain_id ? `  ·  Chain ${data.chain_id}` : ""}
            </Text>
          </View>
          <Speedometer riskLevel={level} size={150} />
        </View>

        {/* No-data warning — only shown if DexScreener also found nothing */}
        {!data.token_name && !data.token_symbol && !data.dexscreener && (
          <View style={[styles.flagRow, { borderLeftColor: "#f97316", backgroundColor: "#f9731615", marginBottom: 10 }]}>
            <Text style={[styles.flagText, { color: "#f97316" }]}>
              ⚠ No data found for this contract. This may mean the token is too new, unindexed, or the contract address is incorrect. Absence of flags does not mean the token is safe — verify independently before trading.
            </Text>
          </View>
        )}

        {/* DexScreener market data — shown when primary source has no security data */}
        {data.dexscreener && (
          <View style={{ marginBottom: 12 }}>
            <Text style={styles.sectionLabel}>Market Data</Text>
            {data.dexscreener.price_usd && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Price</Text>
                <Text style={styles.detailValue}>${parseFloat(data.dexscreener.price_usd).toFixed(4)}</Text>
              </View>
            )}
            {data.dexscreener.liquidity_usd && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Liquidity</Text>
                <Text style={styles.detailValue}>${Number(data.dexscreener.liquidity_usd).toLocaleString("en-US", { maximumFractionDigits: 0 })}</Text>
              </View>
            )}
            {data.dexscreener.volume_24h && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Volume 24h</Text>
                <Text style={styles.detailValue}>${Number(data.dexscreener.volume_24h).toLocaleString("en-US", { maximumFractionDigits: 0 })}</Text>
              </View>
            )}
            {data.dexscreener.dex && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>DEX</Text>
                <Text style={styles.detailValue}>{data.dexscreener.dex}</Text>
              </View>
            )}
          </View>
        )}

        {/* Flags */}
        {critical.length > 0 && (
          <>
            <Text style={[styles.flagHeader, { color: "#ef4444" }]}>🚨 Critical Flags</Text>
            {critical.map((f: string, i: number) => (
              <View key={i} style={[styles.flagRow, { borderLeftColor: "#ef4444" }]}>
                <Text style={styles.flagText}>{f}</Text>
              </View>
            ))}
          </>
        )}
        {warnings.length > 0 && (
          <>
            <Text style={[styles.flagHeader, { color: "#f97316" }]}>⚠ Warning Flags</Text>
            {warnings.map((f: string, i: number) => (
              <View key={i} style={[styles.flagRow, { borderLeftColor: "#f97316" }]}>
                <Text style={styles.flagText}>{f}</Text>
              </View>
            ))}
          </>
        )}
        {data.token_name && critical.length === 0 && warnings.length === 0 && (
          <View style={styles.cleanBanner}>
            <Text style={styles.cleanText}>✓ No honeypot, tax, or ownership flags detected</Text>
          </View>
        )}

        {/* Contract details */}
        {data.raw && (
          <>
            <Text style={styles.sectionLabel}>Contract Details</Text>
            {[
              ["Honeypot",          data.raw.is_honeypot             == 1 ? "🚨 YES — cannot sell" : "No",         "Contract traps buyers — you can buy but never sell"],
              ["Rug Pull Risk",     data.raw.can_take_back_ownership == 1 ? "🚨 YES" : data.raw.owner_change_balance == 1 ? "⚠ Possible" : "No", "Owner can drain liquidity or reclaim tokens"],
              ["Can't Sell",        data.raw.cannot_sell_all         == 1 ? "🚨 YES" : "No",                        "Transfer restrictions prevent holders from selling"],
              ["Buy Tax",           Number(data.raw.buy_tax)  > 0 ? `⚠ ${data.raw.buy_tax}%` : "None",             "Fee taken on every buy — high tax is a red flag"],
              ["Sell Tax",          Number(data.raw.sell_tax) > 0 ? `⚠ ${data.raw.sell_tax}%` : "None",            "Fee taken on every sell — high tax traps holders"],
              ["Tax Modifiable",    data.raw.slippage_modifiable     == 1 ? "⚠ Yes" : "No",                        "Owner can raise buy/sell tax at any time"],
              ["Mintable",          data.raw.is_mintable             == 1 ? "⚠ Yes" : "No",                        "Owner can mint unlimited new tokens, diluting holders"],
              ["Transfer Pausable", data.raw.transfer_pausable       == 1 ? "⚠ Yes" : "No",                        "Owner can freeze all transfers"],
              ["Hidden Owner",      data.raw.hidden_owner            == 1 ? "⚠ Yes" : "No",                        "Real owner is concealed — ownership not transparent"],
              ["Self Destruct",     data.raw.selfdestruct            == 1 ? "🚨 Yes" : "No",                        "Contract can be destroyed, wiping all balances"],
              ["Open Source",       data.raw.is_open_source          == 1 ? "Yes" : "⚠ No — unverified",           "Unverified contracts hide malicious logic"],
              ["Proxy Contract",    data.raw.is_proxy                == 1 ? "⚠ Yes" : "No",                        "Owner can silently upgrade contract logic"],
            ].map(([label, val, tip]) => {
              const isDanger = (val as string).includes("🚨");
              const isWarn   = (val as string).includes("⚠");
              return (
                <View key={label as string} style={styles.detailRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.detailLabel}>{label}</Text>
                    <Text style={styles.detailTip}>{tip}</Text>
                  </View>
                  <Text style={[styles.detailVal, isDanger ? { color: "#ef4444" } : isWarn ? { color: "#f97316" } : {}]}>{val}</Text>
                </View>
              );
            })}
          </>
        )}
      </View>
    );
  }

  // Airdrop scam check
  if (type === "airdrop") {
    const isScam    = data.raw?.is_airdrop_scam == 1;
    const critical  = data.critical_flags || [];
    const warnings  = data.warning_flags  || [];
    const hasIssues = isScam || critical.length > 0;
    const color     = isScam ? "#ef4444" : hasIssues ? "#f97316" : "#22c55e";
    const AIRDROP_RISKS = [
      ["Airdrop Scam",       data.raw?.is_airdrop_scam    == 1 ? "🚨 CONFIRMED SCAM" : "No",  "Token designed to steal from claimants"],
      ["Fake Token",         data.raw?.fake_token          == 1 ? "🚨 YES" : "No",             "Impersonates a legitimate token"],
      ["Can't Sell",         data.raw?.cannot_sell_all     == 1 ? "🚨 YES" : "No",             "Tokens received cannot be sold — trap"],
      ["Hidden Owner",       data.raw?.hidden_owner        == 1 ? "⚠ Yes" : "No",              "Anonymous deployer — unaccountable"],
      ["Honeypot",           data.raw?.is_honeypot         == 1 ? "🚨 YES" : "No",             "Appears claimable but funds are locked"],
      ["Transfer Pausable",  data.raw?.transfer_pausable   == 1 ? "⚠ Yes" : "No",              "Owner can freeze your tokens after claim"],
      ["Mintable",           data.raw?.is_mintable         == 1 ? "⚠ Yes" : "No",              "Supply can be inflated, diluting claim value"],
      ["Sell Tax",           Number(data.raw?.sell_tax) > 50 ? `🚨 ${data.raw.sell_tax}%` : Number(data.raw?.sell_tax) > 10 ? `⚠ ${data.raw.sell_tax}%` : "Normal", "Extreme sell tax traps claimed tokens"],
    ];
    return (
      <View style={styles.resultCard}>
        <View style={[styles.airdropBanner, { borderColor: color + "60", backgroundColor: color + "12" }]}>
          <Text style={styles.airdropIcon}>{isScam ? "🚨" : hasIssues ? "⚠" : "✅"}</Text>
          <View style={{ flex: 1 }}>
            <Text style={[styles.airdropVerdict, { color }]}>
              {isScam ? "AIRDROP SCAM DETECTED" : hasIssues ? "SUSPICIOUS — EXERCISE CAUTION" : "No Airdrop Scam Signals"}
            </Text>
            <Text style={styles.airdropName}>{data.token_name || "Unknown Token"} {data.token_symbol ? `(${data.token_symbol})` : ""}</Text>
            {data.holder_count && <Text style={styles.airdropMeta}>{parseInt(data.holder_count).toLocaleString()} holders</Text>}
          </View>
          <Speedometer riskLevel={isScam ? "CRITICAL" : hasIssues ? "HIGH" : "LOW"} size={110} />
        </View>
        {(critical.length > 0 || warnings.length > 0) && (
          <View style={{ marginBottom: 10 }}>
            {critical.map((f: string, i: number) => <Text key={i} style={styles.critFlag}>🚨 {f}</Text>)}
            {warnings.map((f: string, i: number) => <Text key={i} style={styles.warnFlag}>⚠ {f}</Text>)}
          </View>
        )}
        <Text style={styles.sectionLabel}>Airdrop Risk Signals</Text>
        {AIRDROP_RISKS.map(([label, val, tip]) => {
          const isDanger = (val as string).includes("🚨");
          const isWarn   = (val as string).includes("⚠");
          return (
            <View key={label as string} style={styles.detailRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.detailLabel}>{label}</Text>
                <Text style={styles.detailTip}>{tip}</Text>
              </View>
              <Text style={[styles.detailVal, isDanger ? { color: "#ef4444" } : isWarn ? { color: "#f97316" } : {}]}>{val}</Text>
            </View>
          );
        })}
        <View style={[styles.airdropAdvice, { borderColor: color + "40" }]}>
          <Text style={[styles.airdropAdviceText, { color }]}>
            {isScam
              ? "Do not claim or interact with this token. Importing it to your wallet may trigger malicious contract calls."
              : hasIssues
              ? "Proceed with caution. Research the issuer before claiming. Do not approve spend on unfamiliar tokens."
              : "No scam signals detected. Standard due diligence still recommended before claiming."}
          </Text>
        </View>
      </View>
    );
  }

  if (type === "dapp") {
    const level = (data.risk_level ?? "LOW").toUpperCase();
    const color = level === "CRITICAL" ? "#ef4444" : level === "HIGH" ? "#f97316" : level === "MEDIUM" ? "#facc15" : "#22c55e";
    const flags: string[] = data.risk_flags ?? [];
    const ll = data.defillama;
    const protocolName = ll?.name ?? "";
    const displayTitle = protocolName
      ? `${protocolName} — ${data.phishing ? "Phishing Detected" : level === "LOW" ? "Appears Safe" : `Risk: ${level}`}`
      : data.phishing ? "Phishing Site Detected" : level === "LOW" ? "dApp Appears Safe" : `Risk: ${level}`;
    return (
      <View style={styles.resultCard}>
        <View style={[styles.infoBanner, { borderColor: color + "60", backgroundColor: color + "10" }]}>
          <Text style={{ fontSize: 26 }}>{data.phishing ? "🚨" : level === "LOW" ? "✅" : "⚠️"}</Text>
          <View style={{ flex: 1, paddingLeft: 12 }}>
            <Text style={[styles.infoTitle, { color }]}>{displayTitle}</Text>
            <Text style={styles.infoSub}>{data.url}</Text>
          </View>
        </View>

        {/* DeFiLlama protocol card */}
        {ll && (
          <View style={{ marginBottom: 12 }}>
            <Text style={styles.sectionLabel}>Protocol Intelligence</Text>
            {ll.category && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Category</Text>
                <Text style={styles.detailValue}>{ll.category}</Text>
              </View>
            )}
            {ll.tvl_usd != null && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>TVL</Text>
                <Text style={styles.detailValue}>${(ll.tvl_usd / 1e6).toFixed(0)}M</Text>
              </View>
            )}
            {ll.audits > 0 && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Security Audits</Text>
                <Text style={[styles.detailValue, { color: "#22c55e" }]}>✓ {ll.audits} audit{ll.audits > 1 ? "s" : ""}</Text>
              </View>
            )}
            {ll.chains?.length > 0 && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Chains</Text>
                <Text style={styles.detailValue}>{ll.chains.slice(0, 5).join(", ")}</Text>
              </View>
            )}
          </View>
        )}

        {[
          ["Phishing",    data.phishing ? "🚨 YES — do not connect" : "No",          "Confirmed phishing domain in RelayShield threat corpus"],
          ["Open Source", data.is_open_source ? "✓ Audited" : "⚠ Unverified",        "Audited open-source contracts reduce exploit risk"],
          ["Trust Listed",data.trust_list ? "✓ Known safe dApp" : "Not verified",    "Listed in curated safe dApp registry"],
        ].map(([label, val, tip]) => (
          <View key={label as string} style={styles.detailRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.detailLabel}>{label}</Text>
              <Text style={styles.detailTip}>{tip}</Text>
            </View>
            <Text style={[styles.detailVal, (val as string).includes("🚨") ? { color: "#ef4444" } : (val as string).includes("⚠") ? { color: "#f97316" } : { color: "#22c55e" }]}>{val}</Text>
          </View>
        ))}
        {flags.length > 0 && (
          <>
            <Text style={[styles.flagHeader, { color: "#f97316" }]}>⚠ Risk Flags</Text>
            {flags.map((f: string, i: number) => (
              <View key={i} style={[styles.flagRow, { borderLeftColor: "#f97316" }]}>
                <Text style={styles.flagText}>{f}</Text>
              </View>
            ))}
          </>
        )}
      </View>
    );
  }

  if (type === "nftsecurity") {
    const level = (data.risk_level ?? "LOW").toUpperCase();
    const color = level === "HIGH" ? "#ef4444" : level === "MEDIUM" ? "#facc15" : "#22c55e";
    const flags: string[] = data.risk_flags ?? [];
    const name = data.nft_name || data.nft_symbol || "NFT Contract";
    return (
      <View style={styles.resultCard}>
        <View style={[styles.infoBanner, { borderColor: color + "60", backgroundColor: color + "10" }]}>
          <Text style={{ fontSize: 26 }}>{level === "LOW" ? "✅" : level === "HIGH" ? "🚨" : "⚠️"}</Text>
          <View style={{ flex: 1, paddingLeft: 12 }}>
            <Text style={[styles.infoTitle, { color }]}>{name} — Risk: {level}</Text>
            <Text style={styles.infoSub}>{data.contract_address}</Text>
          </View>
        </View>
        {flags.length > 0 ? (
          <>
            <Text style={[styles.flagHeader, { color: "#ef4444" }]}>🚨 Risk Flags</Text>
            {flags.map((f: string, i: number) => (
              <View key={i} style={[styles.flagRow, { borderLeftColor: "#ef4444" }]}>
                <Text style={styles.flagText}>{f}</Text>
              </View>
            ))}
          </>
        ) : (
          <Text style={styles.cleanText}>✓ No known malicious contract flags found</Text>
        )}
      </View>
    );
  }

  if (type === "nft") {
    const level  = (data.risk_level ?? "LOW").toUpperCase();
    const color  = level === "CRITICAL" ? "#ef4444" : level === "HIGH" ? "#f97316" : level === "MEDIUM" ? "#facc15" : "#22c55e";
    const flags: string[] = data.risk_flags ?? [];
    const sym    = (data.floor_symbol ?? (data.chain === "solana" ? "SOL" : "ETH"));
    const mkt    = data.marketplace === "opensea" ? "OpenSea" : data.marketplace === "magic_eden" ? "Magic Eden" : "";
    const rows: [string, string, string][] = [
      ["Floor price",   `${data.floor ?? data.floor_sol ?? "—"} ${sym}`,    "Current lowest listing price"],
      ["Volume 24h",    data.volume_24h != null ? `${data.volume_24h} ${sym}` : "—", "Trading volume in last 24 hours"],
      ["Volume (all)",  data.volume_all != null ? `${data.volume_all} ${sym}` : "—", "Cumulative trading volume"],
      ...(data.listed != null     ? [["Listed count", `${data.listed}`, "Number of active listings"] as [string,string,string]] : []),
      ...(data.sales_24h != null  ? [["Sales 24h",    `${data.sales_24h}`, "Number of sales in last 24 hours"] as [string,string,string]] : []),
    ];
    return (
      <View style={styles.resultCard}>
        <View style={[styles.infoBanner, { borderColor: color + "60", backgroundColor: color + "10" }]}>
          <Text style={{ fontSize: 26 }}>{level === "CRITICAL" ? "🚨" : level === "LOW" ? "✅" : "⚠️"}</Text>
          <View style={{ flex: 1, paddingLeft: 12 }}>
            <Text style={[styles.infoTitle, { color }]}>{data.symbol} — {level} RISK</Text>
            <Text style={styles.infoSub}>
              Floor: {data.floor ?? data.floor_sol ?? "—"} {sym}{mkt ? ` · ${mkt}` : ""}
            </Text>
          </View>
        </View>
        {rows.map(([label, val, tip]) => (
          <View key={label} style={styles.detailRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.detailLabel}>{label}</Text>
              <Text style={styles.detailTip}>{tip}</Text>
            </View>
            <Text style={styles.detailVal}>{val}</Text>
          </View>
        ))}
        {flags.length > 0 && (
          <>
            <Text style={[styles.flagHeader, { color }]}>⚠ Risk Flags</Text>
            {flags.map((f: string, i: number) => (
              <View key={i} style={[styles.flagRow, { borderLeftColor: color }]}>
                <Text style={styles.flagText}>{f}</Text>
              </View>
            ))}
          </>
        )}
      </View>
    );
  }

  // TON address result
  if (type === "ton") {
    const rc    = riskColor(data.risk_level || "LOW");
    const tok   = data.token;
    const flags: string[] = data.risk_flags ?? data.risk_factors ?? [];
    if (tok) {
      // Token contract
      return (
        <View style={styles.resultCard}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 14 }}>
            <Text style={{ fontSize: 32 }}>💎</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.tokenName}>{tok.token_name || "TON Token"}{tok.token_symbol ? ` (${tok.token_symbol})` : ""}</Text>
              <Text style={styles.tokenMeta}>{data.address}</Text>
            </View>
            <View style={[styles.flagRow, { borderLeftColor: rc, backgroundColor: rc + "15" }]}>
              <Text style={[styles.flagText, { color: rc, fontWeight: "700" }]}>{data.risk_level || "LOW"}</Text>
            </View>
          </View>
          <View style={{ marginTop: 4 }}>
            <Text style={styles.sectionLabel}>Market Data</Text>
            {tok.price_usd && <View style={styles.detailRow}><Text style={styles.detailLabel}>Price</Text><Text style={styles.detailValue}>${parseFloat(tok.price_usd).toFixed(4)}</Text></View>}
            {tok.liquidity_usd && <View style={styles.detailRow}><Text style={styles.detailLabel}>Liquidity</Text><Text style={styles.detailValue}>${Number(tok.liquidity_usd).toLocaleString("en-US", { maximumFractionDigits: 0 })}</Text></View>}
            {tok.volume_24h && <View style={styles.detailRow}><Text style={styles.detailLabel}>Volume 24h</Text><Text style={styles.detailValue}>${Number(tok.volume_24h).toLocaleString("en-US", { maximumFractionDigits: 0 })}</Text></View>}
            {tok.dex && <View style={styles.detailRow}><Text style={styles.detailLabel}>DEX</Text><Text style={styles.detailValue}>{tok.dex}</Text></View>}
          </View>
          <View style={styles.cleanBanner}><Text style={styles.cleanText}>✓ No scam signals detected for this TON token</Text></View>
        </View>
      );
    }
    // Wallet address
    return (
      <View style={styles.resultCard}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <Text style={{ fontSize: 32 }}>💎</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.tokenName}>TON Wallet</Text>
            <Text style={styles.tokenMeta}>{data.balance_ton != null ? `${data.balance_ton} TON` : data.balance ?? ""}{data.state ? ` · ${data.state}` : ""}</Text>
          </View>
          <View style={[styles.flagRow, { borderLeftColor: rc, backgroundColor: rc + "15" }]}>
            <Text style={[styles.flagText, { color: rc, fontWeight: "700" }]}>{data.risk_level || "LOW"}</Text>
          </View>
        </View>
        {flags.length > 0
          ? flags.map((f: string, i: number) => <Text key={i} style={styles.factor}>• {f}</Text>)
          : <View style={styles.cleanBanner}><Text style={styles.cleanText}>✓ No scam signals detected for this TON address</Text></View>
        }
      </View>
    );
  }

  // Base token — reuse token renderer with Base labelling
  if (type === "base") {
    return <ScanResult result={{ type: "token", data }} />;
  }

  if (type === "xrp") {
    const rc = riskColor(data.risk_level || "LOW");
    const flags: string[] = data.risk_flags ?? [];
    return (
      <View style={styles.resultCard}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <Text style={{ fontSize: 32 }}>⚡</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.tokenName}>XRP Wallet</Text>
            <Text style={styles.tokenMeta}>{data.balance_xrp != null ? `${data.balance_xrp} XRP` : ""}{data.owner_count != null ? ` · ${data.owner_count} owned objects` : ""}</Text>
          </View>
          <View style={[styles.flagRow, { borderLeftColor: rc, backgroundColor: rc + "15" }]}>
            <Text style={[styles.flagText, { color: rc, fontWeight: "700" }]}>{data.risk_level || "LOW"}</Text>
          </View>
        </View>
        {flags.length > 0
          ? flags.map((f: string, i: number) => <Text key={i} style={styles.factor}>• {f}</Text>)
          : <View style={styles.cleanBanner}><Text style={styles.cleanText}>✓ No fraud advisory on record for this XRP address</Text></View>
        }
      </View>
    );
  }

  // SOL token risk
  if (type === "sol") {
    const level = (data.risk_level ?? "LOW").toUpperCase();
    const isUnknown = level === "UNKNOWN";
    const rc = level === "CRITICAL" ? "#ef4444" : level === "HIGH" ? "#f97316" : level === "MEDIUM" ? "#facc15" : isUnknown ? "#64748b" : "#22c55e";
    const flags: string[] = data.risk_flags ?? [];
    const ds = data.dexscreener;
    const tokenName = data.token_name || data.name || "Solana Token";
    const tokenSymbol = data.token_symbol || "";
    return (
      <View style={styles.resultCard}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <Text style={{ fontSize: 32 }}>◎</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.tokenName}>{tokenName}{tokenSymbol ? ` (${tokenSymbol})` : ""}</Text>
            <Text style={styles.tokenMeta}>{data.mint ?? ""}</Text>
          </View>
          <View style={[styles.flagRow, { borderLeftColor: rc, backgroundColor: rc + "15" }]}>
            <Text style={[styles.flagText, { color: rc, fontWeight: "700" }]}>{level}</Text>
          </View>
        </View>
        {!isUnknown && data.verification_status && (() => {
          const vs = data.verification_status;
          const vLabel = vs === "jupiter_strict" ? "✓ Verified (Jupiter Strict List)"
                       : vs === "jupiter_verified" ? "◐ Verified (Jupiter Basic)"
                       : "○ Not on any verification registry";
          const vColor = vs === "jupiter_strict" ? "#22c55e" : vs === "jupiter_verified" ? "#facc15" : "#64748b";
          return (
            <View style={[styles.flagRow, { borderLeftColor: vColor, backgroundColor: vColor + "10", marginBottom: 10 }]}>
              <Text style={[styles.flagText, { color: vColor }]}>{vLabel}</Text>
            </View>
          );
        })()}
        {isUnknown
          ? <View style={[styles.flagRow, { borderLeftColor: "#64748b", backgroundColor: "#64748b15" }]}>
              <Text style={styles.flagText}>{data.note || "No data found for this mint — verify independently before trading."}</Text>
            </View>
          : flags.length > 0
          ? <>
              <Text style={[styles.flagHeader, { color: rc }]}>⚠ Risk Flags</Text>
              {flags.map((f: string, i: number) => (
                <View key={i} style={[styles.flagRow, { borderLeftColor: rc }]}>
                  <Text style={styles.flagText}>{f}</Text>
                </View>
              ))}
            </>
          : <View style={styles.cleanBanner}><Text style={styles.cleanText}>✓ No risk signals detected for this Solana token</Text></View>
        }
        {ds && (
          <View style={{ marginTop: 12 }}>
            <Text style={styles.sectionLabel}>Market Data</Text>
            {ds.price_usd && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Price</Text>
                <Text style={styles.detailValue}>${parseFloat(ds.price_usd).toFixed(4)}</Text>
              </View>
            )}
            {ds.liquidity_usd && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Liquidity</Text>
                <Text style={styles.detailValue}>${Number(ds.liquidity_usd).toLocaleString("en-US", { maximumFractionDigits: 0 })}</Text>
              </View>
            )}
            {ds.volume_24h && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Volume 24h</Text>
                <Text style={styles.detailValue}>${Number(ds.volume_24h).toLocaleString("en-US", { maximumFractionDigits: 0 })}</Text>
              </View>
            )}
            {ds.dex && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>DEX</Text>
                <Text style={styles.detailValue}>{ds.dex}</Text>
              </View>
            )}
          </View>
        )}
      </View>
    );
  }

  // BNB token — reuse token renderer with BSC labelling
  if (type === "bnb") {
    return <ScanResult result={{ type: "token", data }} />;
  }

  return (
    <View style={styles.resultCard}>
      <Text style={styles.resultTitle}>Scan Result</Text>
      <Text style={styles.resultSummary}>{JSON.stringify(data, null, 2)}</Text>
    </View>
  );
}

function DimBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min(100, (value / max) * 100);
  const color = value >= max * 0.8 ? "#ef4444" : value >= max * 0.5 ? "#f97316" : value > 0 ? "#facc15" : "#1e3a5f";
  return (
    <View style={styles.dimRow}>
      <Text style={styles.dimLabel}>{label}</Text>
      <View style={styles.dimTrack}>
        <View style={[styles.dimFill, { width: `${pct}%` as any, backgroundColor: color }]} />
      </View>
      <Text style={[styles.dimVal, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: "#0a1628" },
  title:        { fontSize: 20, fontWeight: "800", color: "#fff", paddingHorizontal: 20, paddingTop: 16 },
  subtitle:     { fontSize: 12, color: "#64748b", paddingHorizontal: 20, marginBottom: 14, marginTop: 2 },
  typeRow:      { flexDirection: "row", paddingHorizontal: 16, gap: 8, marginBottom: 14 },
  typeBtn:      { flex: 1, backgroundColor: "#0F1F3D", borderRadius: 10, paddingVertical: 10, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  typeBtnActive:{ borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  typeIcon:     { fontSize: 18, marginBottom: 3, color: "#e2e8f0" },
  typeLabel:    { fontSize: 10, color: "#64748b", fontWeight: "600", textAlign: "center" },
  inputCard:    { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  input:        { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 13, fontFamily: "monospace", marginBottom: 10 },
  scanBtn:      { backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  scanBtnText:  { color: "#0a1628", fontWeight: "800", fontSize: 14 },
  errorCard:    { backgroundColor: "#ef444420", borderRadius: 10, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#ef444440" },
  errorText:    { color: "#ef4444", fontSize: 13, lineHeight: 20 },
  resultCard:   { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  resultHeader: { flexDirection: "row", alignItems: "center", marginBottom: 14 },
  resultTitle:  { fontSize: 14, fontWeight: "700", color: "#e2e8f0", marginBottom: 4 },
  resultSummary:{ fontSize: 12, color: "#94a3b8", lineHeight: 18 },
  sectionLabel: { fontSize: 10, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginTop: 14, marginBottom: 8 },
  dimRow:       { flexDirection: "row", alignItems: "center", marginBottom: 8, gap: 8 },
  dimLabel:     { fontSize: 11, color: "#94a3b8", width: 130 },
  dimTrack:     { flex: 1, height: 6, backgroundColor: "#0a1628", borderRadius: 3, overflow: "hidden" },
  dimFill:      { height: "100%", borderRadius: 3 },
  dimVal:       { fontSize: 11, fontWeight: "700", width: 24, textAlign: "right" },
  factor:       { fontSize: 12, color: "#94a3b8", lineHeight: 20, marginBottom: 4 },
  infoBanner:   { flexDirection: "row", alignItems: "center", padding: 14, borderRadius: 10, borderWidth: 1, backgroundColor: "#060b18" },
  infoTitle:    { fontSize: 15, fontWeight: "800", marginBottom: 4 },
  infoSub:      { fontSize: 12, color: "#94a3b8", lineHeight: 18 },
  chainRow:      { flexDirection: "row", paddingHorizontal: 16, gap: 6, marginBottom: 10, flexWrap: "wrap" },
  chainPill:     { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 16, backgroundColor: "#0F1F3D", borderWidth: 1, borderColor: "#1e3a5f" },
  chainPillActive:{ borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  chainPillText: { fontSize: 11, color: "#64748b", fontWeight: "600" },
  demoNote:     { backgroundColor: "#1e3a5f30", borderRadius: 10, padding: 16, borderWidth: 1, borderColor: "#1e3a5f" },
  demoNoteText: { fontSize: 12, color: "#64748b", lineHeight: 20 },
  tokenHeader:  { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  tokenName:    { fontSize: 16, fontWeight: "800", color: "#e2e8f0", marginBottom: 2 },
  tokenSymbol:  { fontSize: 13, color: "#00B5A5", fontWeight: "700", marginBottom: 4 },
  tokenMeta:    { fontSize: 11, color: "#64748b" },
  flagHeader:   { fontSize: 12, fontWeight: "700", marginTop: 12, marginBottom: 6 },
  flagRow:      { backgroundColor: "#060b18", borderLeftWidth: 3, borderRadius: 6, padding: 10, marginBottom: 6 },
  flagText:     { fontSize: 12, color: "#94a3b8", lineHeight: 18 },
  cleanBanner:  { backgroundColor: "#22c55e15", borderRadius: 8, padding: 12, borderWidth: 1, borderColor: "#22c55e30", marginTop: 8 },
  cleanText:    { fontSize: 13, color: "#22c55e", fontWeight: "600" },
  warningBox:   { backgroundColor: "#ef444415", borderRadius: 8, padding: 12, borderWidth: 1, borderColor: "#ef444430", marginBottom: 10 },
  warningTitle: { fontSize: 13, color: "#ef4444", fontWeight: "600" },
  detailRow:    { flexDirection: "row", justifyContent: "space-between", paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  detailValue:  { fontSize: 12, color: "#e2e8f0", fontWeight: "600", textAlign: "right", flex: 1 },
  detailLabel:  { fontSize: 12, color: "#94a3b8" },
  detailTip:    { fontSize: 10, color: "#94a3b8", marginTop: 1 },
  detailVal:       { fontSize: 12, color: "#e2e8f0", fontWeight: "600", marginLeft: 8, textAlign: "right", maxWidth: 140 },
  airdropBanner:   { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 10, borderWidth: 1, marginBottom: 12 },
  airdropIcon:     { fontSize: 28 },
  airdropVerdict:  { fontSize: 13, fontWeight: "800", marginBottom: 3 },
  airdropName:     { fontSize: 12, color: "#e2e8f0", fontWeight: "600" },
  airdropMeta:     { fontSize: 10, color: "#64748b", marginTop: 2 },
  critFlag:        { fontSize: 12, color: "#ef4444", fontWeight: "700", marginBottom: 4 },
  warnFlag:        { fontSize: 12, color: "#f97316", fontWeight: "600", marginBottom: 4 },
  airdropAdvice:   { marginTop: 14, padding: 12, borderRadius: 8, borderWidth: 1, backgroundColor: "#060b18" },
  airdropAdviceText: { fontSize: 12, lineHeight: 18, fontWeight: "500" },
});
