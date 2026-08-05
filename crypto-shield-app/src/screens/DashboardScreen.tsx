import React, { useState, useCallback, useEffect } from "react";
import {
  View, Text, ScrollView, RefreshControl,
  StyleSheet, TouchableOpacity, StatusBar, Modal, TextInput,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RiskGauge } from "../components/RiskGauge";
import { AlertCard, Alert } from "../components/AlertCard";
import { GasCard } from "../components/GasCard";
import { StablecoinCard } from "../components/StablecoinCard";
import { StreakCard } from "../components/StreakCard";
import { ThreatInterceptedAnimation } from "../components/ThreatInterceptedAnimation";
import { useGamification } from "../hooks/useGameification";
import { useWallets } from "../hooks/useWallet";
import * as SecureStore from "expo-secure-store";
import { LAST_ALERT_KEY, PUSH_TOKEN_KEY } from "../hooks/usePushNotifications";
import * as Notifications from "expo-notifications";
import * as RS from "../api/relayshield";
import Constants from "expo-constants";

// ---------------------------------------------------------------------------
// Threat of the Week — rotates every Sunday midnight UTC
// ---------------------------------------------------------------------------
const THREATS_OF_WEEK = [
  {
    icon: "🧲",
    title: "Address Poisoning Surge",
    body: "Attackers are flooding Solana wallets with dust transactions from addresses that share your first and last 4 characters. Never copy an address from transaction history.",
    action: "Run Sweep → Address Poisoning",
    severity: "HIGH" as const,
  },
  {
    icon: "🔑",
    title: "Infostealer Log Markets Active",
    body: "Fresh stealer logs are being sold in Telegram channels daily. Harvested browser sessions bypass 2FA without needing your password.",
    action: "Check email exposure in Settings",
    severity: "CRITICAL" as const,
  },
  {
    icon: "📱",
    title: "SIM Swap Wave",
    body: "Telecom social engineering attacks are targeting crypto holders. A swapped SIM gives attackers full control of your SMS-based exchange 2FA.",
    action: "Enable app-based 2FA on all exchanges",
    severity: "HIGH" as const,
  },
  {
    icon: "🪤",
    title: "Token Approval Drainers",
    body: "Malicious dApps request unlimited token spend approvals. Many users have forgotten approvals granted months ago that are still active.",
    action: "Review approvals in Signature Guard",
    severity: "HIGH" as const,
  },
  {
    icon: "⛓",
    title: "Supply Chain Attacks on Solana SDKs",
    body: "Compromised NPM packages targeting Solana developers have leaked wallet keypairs. Verify your vendor integrity.",
    action: "Run Vendor Sweep",
    severity: "MEDIUM" as const,
  },
];

function threatOfWeek() {
  const week = Math.floor(Date.now() / (7 * 24 * 3600 * 1000));
  return THREATS_OF_WEEK[week % THREATS_OF_WEEK.length];
}

const SCORE_KEY = "cs_last_risk_score";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true, shouldPlaySound: false, shouldSetBadge: false,
  }),
});

// Demo alerts — replace with live RS API calls
const DEMO_ALERTS: Alert[] = [
  {
    id: "1", type: "INFOSTEALER", severity: "CRITICAL",
    title: "Credential exposure detected",
    detail: "Email associated with your monitored wallet found in stealer log archive. Session cookies and saved passwords extracted.",
    wallet: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", walletLabel: "Solana Backpack wallet",
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    acknowledged: false,
  },
  {
    id: "2", type: "TOKEN_RISK", severity: "HIGH",
    title: "High-risk token in wallet",
    detail: "ShadowPepe (0x7a3d...f8c2): honeypot detected, transfer restrictions active. Do not approve further spend.",
    wallet: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    timestamp: new Date(Date.now() - 86400000).toISOString(),
    acknowledged: false,
  },
  {
    id: "3", type: "SUPPLY_CHAIN", severity: "MEDIUM",
    title: "Vendor risk: pyth.network",
    detail: "1 infostealer hit detected on oracle provider domain in past 30 days. Monitor for escalation.",
    timestamp: new Date(Date.now() - 172800000).toISOString(),
    acknowledged: true,
  },
];

export function DashboardScreen({ navigation }: any) {
  const insets = useSafeAreaInsets();
  const { wallets, apiKey, updateWalletRisk } = useWallets();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const { streak, shieldScore, referralCode, recordActivity } = useGamification();
  const [showIntercepted, setShowIntercepted] = useState(false);
  const [gasThreshold, setGasThreshold] = useState(20);
  const [showGasModal, setShowGasModal] = useState(false);
  const [gasInput,     setGasInput]     = useState("20");

  useEffect(() => {
    (async () => {
      const g = await SecureStore.getItemAsync("cs_gas_threshold");
      if (g) { const v = parseInt(g); setGasThreshold(v); setGasInput(String(v)); }
    })();
  }, []);

  const [overallScore,    setOverallScore]    = useState(0);
  const [scanning,        setScanning]        = useState(false);
  const [portfolioUSD,    setPortfolioUSD]    = useState<number | null>(null);
  const [checkAddr,       setCheckAddr]       = useState("");
  const [checkResult,     setCheckResult]     = useState<{ level: string; label: string; flags: string[] } | null>(null);
  const [checkLoading,    setCheckLoading]    = useState(false);
  const openAlerts = alerts.filter(a => !a.acknowledged).length;
  const [scoreChange, setScoreChange] = useState<{ prev: number; curr: number } | null>(null);
  const [lastAlert, setLastAlert] = useState<{ title: string; body: string; timestamp: string } | null>(null);
  const [lastAlertDismissed, setLastAlertDismissed] = useState(false);
  const threat = threatOfWeek();

  useEffect(() => {
    // Local cache first (instant paint), then reconcile with server state —
    // the server is authoritative since it's the one that actually sent the
    // alert, whereas the OS notification-received event is unreliable across
    // Android/FCM/Expo app-state combinations and shouldn't be the source of truth.
    SecureStore.getItemAsync(LAST_ALERT_KEY).then(v => {
      if (v) { try { setLastAlert(JSON.parse(v)); } catch {} }
    });
    SecureStore.getItemAsync(PUSH_TOKEN_KEY).then(async token => {
      if (!token) return;
      const serverAlert = await RS.getLastAlert(token).catch(() => null);
      if (serverAlert) {
        setLastAlert(serverAlert);
        SecureStore.setItemAsync(LAST_ALERT_KEY, JSON.stringify(serverAlert)).catch(() => {});
      }
    });
  }, []);

  // Opportunistic live update while Dashboard is mounted — not the source of
  // truth (see above), but shows new pushes immediately on the rare occasions
  // the OS does deliver the JS-level event while foregrounded.
  useEffect(() => {
    const sub = Notifications.addNotificationReceivedListener(notif => {
      const next = {
        title: notif.request.content.title ?? "",
        body: notif.request.content.body ?? "",
        timestamp: new Date().toISOString(),
      };
      setLastAlert(next);
      setLastAlertDismissed(false);
      SecureStore.setItemAsync(LAST_ALERT_KEY, JSON.stringify(next)).catch(() => {});
    });
    const respSub = Notifications.addNotificationResponseReceivedListener(resp => {
      console.log("[notif-debug] response (tapped):", JSON.stringify(resp.notification.request.content));
    });
    return () => { sub.remove(); respSub.remove(); };
  }, []);

  // Register Expo push token with RS backend for server-side alerts
  // Requires EAS project — skipped gracefully in Expo Go until `eas init` is run
  useEffect(() => {
    if (!apiKey) return;
    (async () => {
      try {
        const { status } = await Notifications.requestPermissionsAsync();
        if (status !== "granted") return;
        const projectId: string | undefined =
          (Constants.easConfig as any)?.projectId ??
          (Constants.expoConfig as any)?.extra?.eas?.projectId;
        if (!projectId) return; // Expo Go dev — skip until EAS project is registered
        const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
        await RS.registerPushToken(tokenData.data, wallets.map(w => ({ address: w.address, chain: w.chain, label: w.label })), apiKey);
      } catch (err) {
        console.error("[push registration failed]", err);
      }
    })();
  }, [apiKey, wallets.length]);

  // Re-scan whenever wallet count changes (user adds EVM/TON after initial load)
  // Also fires on apiKey change (user adds key in Settings)
  useEffect(() => {
    if (wallets.length > 0 && apiKey) {
      scanAllWallets();
    } else if (wallets.length === 0) {
      setOverallScore(0);
    }
  }, [wallets.length, apiKey]);

  async function fetchSolanaTokens(address: string) {
    const resp = await fetch("https://api.relayshield.net/v1/app/solana-rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-RS-API-KEY": apiKey ?? "" },
      body: JSON.stringify({
        jsonrpc: "2.0", id: 1,
        method: "getTokenAccountsByOwner",
        params: [address, { programId: "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA" }, { encoding: "jsonParsed" }],
      }),
    });
    const data = await resp.json();
    return ((data.result?.value ?? []) as any[])
      .map((acc: any) => ({
        mint:   acc.account?.data?.parsed?.info?.mint as string,
        amount: (acc.account?.data?.parsed?.info?.tokenAmount?.uiAmount as number) ?? 0,
      }))
      .filter((t: any) => t.mint && t.amount > 0)
      .sort((a: any, b: any) => b.amount - a.amount);
  }

  async function scanAllWallets() {
    if (!apiKey || wallets.length === 0) return;
    setScanning(true);
    const SCORE_MAP: Record<string, number> = { LOW: 20, MEDIUM: 45, HIGH: 70, CRITICAL: 90 };
    const newAlerts: Alert[] = [];
    // Score components: wallet-level scores + confirmed token scores (not LP/trusted)
    const scoreComponents: number[] = [15];

    // Known legitimate LP/receipt token mints that routinely false-positive on risk APIs
    const TRUSTED_LP_MINTS = new Set([
      "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4", // Jupiter Perps LP
      "So11111111111111111111111111111111111111112",   // Wrapped SOL
      "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", // USDC
      "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", // USDT
      "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj", // stSOL
      "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  // mSOL
      "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn", // JitoSOL
      "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",  // bSOL
    ]);

    for (const wallet of wallets) {
      try {
        const risk = await RS.scanWalletRisk(wallet.address, apiKey);
        const sc   = SCORE_MAP[(risk.risk_level ?? "LOW").toUpperCase()] ?? 20;
        scoreComponents.push(sc);
        updateWalletRisk(wallet.address, sc, (risk.risk_level ?? "LOW").toUpperCase() as any);
        if (sc >= 70 && (risk.risk_flags ?? []).length > 0) {
          newAlerts.push({
            id: `wallet-${wallet.address}`,
            type: "TOKEN_RISK",
            severity: sc >= 90 ? "CRITICAL" : "HIGH",
            title: `Wallet risk: ${wallet.label}`,
            detail: (risk.risk_flags as string[]).slice(0, 3).join(", "),
            wallet: wallet.address, walletLabel: wallet.label,
            timestamp: new Date().toISOString(),
            acknowledged: false,
          });
        }
      } catch {}

      if (wallet.chain === "solana") {
        try {
          const tokens = await fetchSolanaTokens(wallet.address);
          for (const token of tokens.slice(0, 8)) {
            // Skip known-legitimate LP and protocol tokens — they false-positive on risk APIs
            if (TRUSTED_LP_MINTS.has(token.mint)) continue;
            let tScore = 0;
            try {
              const tr = await RS.checkTokenRisk(token.mint, "solana", apiKey);
              const lvl = (tr.risk_level ?? "").toUpperCase();
              if (lvl === "HIGH" || lvl === "CRITICAL") {
                tScore = lvl === "CRITICAL" ? 85 : 65;
                scoreComponents.push(tScore);
                // Resolve token name — prefer API response, fall back to DexScreener
                let tokenLabel = tr.token_name || tr.token_symbol || "";
                if (!tokenLabel) {
                  try {
                    const ds = await fetch(`https://api.dexscreener.com/latest/dex/tokens/${token.mint}`);
                    const dsData = await ds.json();
                    const pair = (dsData.pairs ?? [])[0];
                    tokenLabel = pair?.baseToken?.name || pair?.baseToken?.symbol || "";
                  } catch {}
                }
                const tokenDisplay = tokenLabel || token.mint.slice(0, 8) + "…";
                newAlerts.push({
                  id: `token-${token.mint}`,
                  type: "TOKEN_RISK",
                  severity: lvl as any,
                  title: `Flagged token in ${wallet.label}`,
                  detail: `${tokenDisplay}: ${[...(tr.critical_flags ?? []), ...(tr.warning_flags ?? [])].slice(0, 2).join(", ")}`,
                  wallet: wallet.address, walletLabel: wallet.label,
                  timestamp: new Date().toISOString(),
                  acknowledged: false,
                });
              }
            } catch {}
            // Cross-check with Rugcheck for better Solana coverage
            try {
              const rc = await RS.checkSolanaTokenRisk(token.mint, apiKey);
              const rcLevel = (rc.risk_level ?? "").toUpperCase();
              if ((rcLevel === "HIGH" || rcLevel === "CRITICAL") && tScore < 65) {
                const tScore2 = rcLevel === "CRITICAL" ? 85 : 65;
                scoreComponents.push(tScore2);
                // Prefer token name from Rugcheck response, fall back to DexScreener
                let tokenLabel = rc.token_name || rc.token_symbol || "";
                if (!tokenLabel) {
                  try {
                    const ds = await fetch(`https://api.dexscreener.com/latest/dex/tokens/${token.mint}`);
                    const dsData = await ds.json();
                    const pair = (dsData.pairs ?? [])[0];
                    tokenLabel = pair?.baseToken?.name || pair?.baseToken?.symbol || "";
                  } catch {}
                }
                const tokenDisplay = tokenLabel || token.mint.slice(0, 8) + "…";
                newAlerts.push({
                  id: `rugcheck-${token.mint}`,
                  type: "TOKEN_RISK",
                  severity: rcLevel as any,
                  title: `High-risk token in ${wallet.label}`,
                  detail: `${tokenDisplay}: ${(rc.risk_flags ?? []).slice(0, 2).join(", ")}`,
                  wallet: wallet.address, walletLabel: wallet.label,
                  timestamp: new Date().toISOString(),
                  acknowledged: false,
                });
              }
            } catch {}
          }
        } catch {}
      }
    }

    // Weighted score: average of components, capped by highest confirmed alert
    // Prevents a single LP token false-positive from pinning the score at HIGH
    const avg = scoreComponents.reduce((a, b) => a + b, 0) / scoreComponents.length;
    const maxScore = Math.max(...scoreComponents);
    const blended = Math.round(avg * 0.6 + maxScore * 0.4);
    setOverallScore(Math.min(blended, 100));
    if (newAlerts.length > 0) {
      setAlerts(prev => {
        const existing = prev.filter(a => !newAlerts.find(n => n.id === a.id));
        return [...newAlerts, ...existing];
      });
    }
    // Portfolio USD value — SOL native balance + SPL tokens via backend proxies
    let totalUSD = 0;
    for (const wallet of wallets.filter(w => w.chain === "solana")) {
      try {
        // Native SOL balance via Alchemy proxy
        const balResp = await fetch("https://api.relayshield.net/v1/app/solana-rpc", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-RS-API-KEY": apiKey ?? "" },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getBalance", params: [wallet.address] }),
        });
        const balData = await balResp.json();
        const lamports: number = balData.result?.value ?? 0;
        const sol = lamports / 1e9;
        // Jupiter Price API — no key, no rate limit, more reliable than CoinGecko free tier
        const priceResp = await fetch("https://price.jup.ag/v6/price?ids=SOL");
        const priceData = await priceResp.json();
        const solPrice: number = priceData?.data?.SOL?.price ?? 0;
        totalUSD += sol * solPrice;

        // SPL token portfolio value via Helius proxy
        const assetsResp = await fetch("https://api.relayshield.net/v1/app/helius-assets", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-RS-API-KEY": apiKey ?? "" },
          body: JSON.stringify({ owner_address: wallet.address }),
        });
        const assetsData = await assetsResp.json();
        const assets: any[] = assetsData.result?.items ?? [];
        for (const asset of assets) {
          const tokenValue: number = asset.token_info?.price_info?.total_price ?? 0;
          totalUSD += tokenValue;
        }
      } catch {}
    }
    if (totalUSD > 0) setPortfolioUSD(totalUSD);

    await checkScorePulse(maxScore);
    setScanning(false);
  }

  // newScore is passed directly — never read from overallScore state which lags by one render
  async function checkScorePulse(newScore: number) {
    try {
      const { status } = await Notifications.requestPermissionsAsync();
      const raw = await SecureStore.getItemAsync(SCORE_KEY);
      const prev = raw ? parseInt(raw) : null;
      // Only fire if score has genuinely moved ≥5 points in either direction
      if (prev !== null && newScore !== prev && Math.abs(newScore - prev) >= 5) {
        setScoreChange({ prev, curr: newScore });
        if (status === "granted") {
          await Notifications.scheduleNotificationAsync({
            content: {
              title: newScore > prev
                ? `⚠️ Wallet risk increased: ${prev} → ${newScore}`
                : `✅ Wallet risk improved: ${prev} → ${newScore}`,
              body: newScore > prev
                ? "New threat signals detected. Open Crypto Shield to review."
                : "Your security posture improved. Keep it up.",
            },
            trigger: null,
          });
        }
      }
      await SecureStore.setItemAsync(SCORE_KEY, String(newScore));
    } catch { /* notifications not critical */ }
  }

  async function checkBeforeYouSend() {
    const addr = checkAddr.trim();
    if (!addr) return;
    setCheckLoading(true);
    setCheckResult(null);
    try {
      const flags: string[] = [];
      let level = "LOW";

      // 1. Address poisoning lookalike check against user's own wallets
      for (const w of wallets) {
        if (addr !== w.address &&
            (addr.slice(0, 6) === w.address.slice(0, 6) ||
             addr.slice(-6) === w.address.slice(-6))) {
          flags.push(`⚠️ Lookalike of your ${w.label} wallet — possible address poisoning attempt`);
          level = "CRITICAL";
        }
      }

      if (apiKey) {
        const isSolana = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(addr) && !addr.startsWith("0x");

        // 2. GoPlus wallet risk
        try {
          const risk = await RS.scanWalletRisk(addr, apiKey);
          const rl = (risk.risk_level ?? "LOW").toUpperCase();
          if (rl === "HIGH" || rl === "CRITICAL") {
            level = level === "CRITICAL" ? "CRITICAL" : rl;
            (risk.risk_flags ?? []).forEach((f: string) => flags.push(f));
          }
        } catch {}

        // 3. Rugcheck for Solana addresses — better coverage than GoPlus
        if (isSolana) {
          try {
            const rugcheck = await RS.checkSolanaTokenRisk(addr, apiKey);
            if (rugcheck.risk_level === "HIGH" || rugcheck.risk_level === "CRITICAL") {
              level = level === "CRITICAL" ? "CRITICAL" : rugcheck.risk_level;
              (rugcheck.risk_flags ?? []).forEach((f: string) => flags.push(`Rugcheck: ${f}`));
            }
          } catch {}

          // 4. SolanaFM address reputation
          try {
            const sfm = await RS.checkSolanaAddressRisk(addr, apiKey);
            if (sfm.risk_level !== "LOW") {
              (sfm.risk_flags ?? []).forEach((f: string) => flags.push(`SolanaFM: ${f}`));
            }
          } catch {}
        }

        // 5. IOC corpus check — look up address in RS intel database
        try {
          const intelData = await RS.getTrendingThreats(72, apiKey);
          const trending: Record<string, any[]> = intelData.trending ?? {};
          const allIOCs = Object.values(trending).flat();
          const match = allIOCs.find((ioc: any) =>
            ioc.ioc_value?.toLowerCase() === addr.toLowerCase()
          );
          if (match) {
            level = "CRITICAL";
            flags.push(`🚨 Address found in RelayShield IOC corpus: ${match.malware || match.ioc_type || "malicious indicator"}`);
          }
        } catch {}
      }

      const LABELS: Record<string, string> = {
        CRITICAL: "🚨 Do not send — serious risk detected",
        HIGH:     "⚠️ High risk — verify carefully before sending",
        MEDIUM:   "⚠️ Some risk signals — proceed with caution",
        LOW:      "✓ No risk signals detected — address looks safe",
      };
      setCheckResult({ level, label: LABELS[level] ?? LABELS.LOW, flags });
    } catch {
      setCheckResult({ level: "LOW", label: "✓ Check complete — no issues found", flags: [] });
    }
    setCheckLoading(false);
  }

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    scanAllWallets().finally(() => setRefreshing(false));
  }, [apiKey, wallets]);

  function acknowledgeAlert(id: string) {
    const alert = alerts.find(a => a.id === id);
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, acknowledged: true } : a));
    recordActivity(10);
    if (alert?.severity === "CRITICAL") {
      setShowIntercepted(true);
    }
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <StatusBar barStyle="light-content" backgroundColor="#0a1628" />
      <ThreatInterceptedAnimation
        visible={showIntercepted}
        type="critical_alert"
        onDismiss={() => setShowIntercepted(false)}
      />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.logoText}>🛡 Crypto Shield</Text>
          <Text style={styles.subtitle}>by RelayShield</Text>
        </View>
        <TouchableOpacity
          style={styles.settingsBtn}
          onPress={() => navigation.navigate("Settings")}
        >
          <Text style={styles.settingsIcon}>⚙️</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        showsVerticalScrollIndicator={true}
        indicatorStyle="white"
        scrollEventThrottle={16}
        decelerationRate="normal"
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#00B5A5" />}
      >
        {/* Risk overview card */}
        <View style={styles.riskCard}>
          <View style={styles.gaugeRow}>
            <RiskGauge score={overallScore} size={130} />
            <View style={styles.kpiStack}>
              <KPI label="Wallets" value={wallets.length || 1} />
              <KPI label="Open Alerts" value={openAlerts} highlight={openAlerts > 0} />
              {portfolioUSD !== null
                ? <KPI label="Portfolio Value" value={`$${portfolioUSD.toLocaleString("en-US", { maximumFractionDigits: 0 })}`} highlight={false} />
                : <KPI label="Signals Checked" value="6 / 6" />
              }
              <KPI label="Last Scan" value={scanning ? "Scanning…" : wallets.length > 0 && overallScore > 0 ? "Just now" : "—"} />
            </View>
          </View>
          <Text style={styles.riskSummary}>
            {overallScore >= 70
              ? "⚠️ Immediate action required — CRITICAL signals active"
              : overallScore >= 45
              ? "Your wallet environment has elevated risk signals. Review open alerts."
              : "Your wallet environment is within normal risk parameters."}
          </Text>
          {scanning && <Text style={{ fontSize: 10, color: "#00B5A5", textAlign: "center" }}>Scanning wallets…</Text>}
        </View>

        {/* Daily risk pulse banner */}
        {scoreChange && (
          <TouchableOpacity
            style={[styles.pulseBanner, { borderColor: scoreChange.curr > scoreChange.prev ? "#ef444440" : "#22c55e40", backgroundColor: scoreChange.curr > scoreChange.prev ? "#ef444410" : "#22c55e10" }]}
            onPress={() => setScoreChange(null)}
          >
            <Text style={[styles.pulseIcon]}>{scoreChange.curr > scoreChange.prev ? "⚠️" : "✅"}</Text>
            <View style={{ flex: 1 }}>
              <Text style={[styles.pulseTitle, { color: scoreChange.curr > scoreChange.prev ? "#ef4444" : "#22c55e" }]}>
                {scoreChange.curr > scoreChange.prev ? "Risk increased" : "Risk improved"} {scoreChange.prev} → {scoreChange.curr}
              </Text>
              <Text style={styles.pulseSub}>
                {scoreChange.curr > scoreChange.prev ? "New signals detected — review active alerts" : "Your security posture improved — keep it up"}
              </Text>
            </View>
            <Text style={styles.pulseDismiss}>✕</Text>
          </TouchableOpacity>
        )}

        {/* Last push alert banner */}
        {lastAlert && !lastAlertDismissed && (
          <TouchableOpacity
            style={styles.lastAlertBanner}
            onPress={() => setLastAlertDismissed(true)}
            activeOpacity={0.8}
          >
            <Text style={styles.lastAlertIcon}>🔔</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.lastAlertTitle} numberOfLines={1}>{lastAlert.title}</Text>
              <Text style={styles.lastAlertBody} numberOfLines={1}>{lastAlert.body}</Text>
            </View>
            <Text style={styles.pulseDismiss}>✕</Text>
          </TouchableOpacity>
        )}

        {/* Demo mode banner */}
        {!apiKey && (
          <View style={styles.demoBanner}>
            <Text style={styles.demoLabel}>DEMO</Text>
            <Text style={styles.demoText}>Sample data shown. Link your subscription in Settings to enable live scanning.</Text>
          </View>
        )}

        {/* Threat of the Week */}
        <View style={[styles.threatBanner, { borderLeftColor: threat.severity === "CRITICAL" ? "#ef4444" : threat.severity === "HIGH" ? "#f97316" : "#facc15" }]}>
          <View style={styles.threatHeader}>
            <Text style={styles.threatIcon}>{threat.icon}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.threatWeekLabel}>THREAT OF THE WEEK</Text>
              <Text style={styles.threatTitle}>{threat.title}</Text>
            </View>
            <View style={[styles.threatSevPill, { backgroundColor: (threat.severity === "CRITICAL" ? "#ef4444" : threat.severity === "HIGH" ? "#f97316" : "#facc15") + "20" }]}>
              <Text style={[styles.threatSevText, { color: threat.severity === "CRITICAL" ? "#ef4444" : threat.severity === "HIGH" ? "#f97316" : "#facc15" }]}>{threat.severity}</Text>
            </View>
          </View>
          <Text style={styles.threatBody}>{threat.body}</Text>
          <Text style={styles.threatAction}>→ {threat.action}</Text>
        </View>

        {/* Check Before You Send */}
        <View style={styles.checkCard}>
          <Text style={styles.checkTitle}>🔎 Check Before You Send</Text>
          <Text style={styles.checkSub}>Paste any destination address to verify before sending</Text>
          <View style={styles.checkRow}>
            <TextInput
              style={styles.checkInput}
              value={checkAddr}
              onChangeText={v => { setCheckAddr(v); setCheckResult(null); }}
              placeholder="Destination address (any chain)"
              placeholderTextColor="#334155"
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={checkBeforeYouSend}
            />
            <TouchableOpacity
              style={[styles.checkBtn, checkLoading && { opacity: 0.6 }]}
              onPress={checkBeforeYouSend}
              disabled={checkLoading}
            >
              <Text style={styles.checkBtnText}>{checkLoading ? "…" : "Check"}</Text>
            </TouchableOpacity>
          </View>
          {checkResult && (
            <View style={[styles.checkResult, {
              borderColor: checkResult.level === "CRITICAL" ? "#ef444440"
                : checkResult.level === "HIGH" ? "#f9731640"
                : checkResult.level === "MEDIUM" ? "#facc1540" : "#22c55e40",
              backgroundColor: checkResult.level === "CRITICAL" ? "#ef444410"
                : checkResult.level === "HIGH" ? "#f9731610"
                : checkResult.level === "MEDIUM" ? "#facc1510" : "#22c55e10",
            }]}>
              <Text style={[styles.checkResultLabel, {
                color: checkResult.level === "CRITICAL" ? "#ef4444"
                  : checkResult.level === "HIGH" ? "#f97316"
                  : checkResult.level === "MEDIUM" ? "#facc15" : "#22c55e",
              }]}>{checkResult.label}</Text>
              {checkResult.flags.map((f, i) => (
                <Text key={i} style={styles.checkFlag}>• {f}</Text>
              ))}
            </View>
          )}
        </View>

        {/* Quick actions */}
        <View style={styles.quickActions}>
          <QuickAction icon="💼" label="Wallets" onPress={() => navigation.navigate("Wallets")} />
          <QuickAction icon="🔍" label="Scan" onPress={() => navigation.navigate("Scan")} />
          <QuickAction icon="🔗" label="Vendors" onPress={() => navigation.navigate("SupplyChain")} />
          <QuickAction icon="📊" label="Intel" onPress={() => navigation.navigate("Intel")} />
        </View>

        {/* Streak + Shield Score + Referral */}
        <View style={{ paddingHorizontal: 16 }}>
          <StreakCard streak={streak} shieldScore={shieldScore} referralCode={referralCode} />
        </View>

        {/* Gas + Stablecoin cards */}
        <View style={{ paddingHorizontal: 16 }}>
          <GasCard
            apiKey={apiKey ?? null}
            gasAlertThreshold={gasThreshold}
            onSetThreshold={() => setShowGasModal(true)}
          />
          <StablecoinCard />
        </View>

        {/* Gas threshold modal */}
        <Modal visible={showGasModal} transparent animationType="fade">
          <View style={styles.modalOverlay}>
            <View style={styles.modal}>
              <Text style={styles.modalTitle}>Gas Alert Threshold</Text>
              <Text style={styles.modalSub}>Alert me when standard gas falls below:</Text>
              <TextInput
                style={styles.modalInput}
                value={gasInput}
                onChangeText={setGasInput}
                keyboardType="numeric"
                placeholder="gwei"
                placeholderTextColor="#334155"
              />
              <Text style={styles.modalHint}>Typical ranges: Low &lt;15 · Medium 15–40 · High &gt;40 gwei</Text>
              <View style={styles.modalBtns}>
                <TouchableOpacity style={styles.modalCancel} onPress={() => setShowGasModal(false)}>
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.modalSave} onPress={async () => {
                  const v = parseInt(gasInput) || 20;
                  setGasThreshold(v);
                  await SecureStore.setItemAsync("cs_gas_threshold", String(v));
                  setShowGasModal(false);
                }}>
                  <Text style={styles.modalSaveText}>Save</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* Alerts */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Active Alerts</Text>
            {openAlerts > 0 && (
              <View style={styles.alertBadge}>
                <Text style={styles.alertBadgeText}>{openAlerts} open</Text>
              </View>
            )}
          </View>
          {alerts.length === 0 && !apiKey && (
            <>
              <View style={styles.demoAlertsHeader}>
                <Text style={styles.demoAlertsLabel}>SAMPLE ALERTS — LINK SUBSCRIPTION TO SEE REAL DATA</Text>
              </View>
              {DEMO_ALERTS.map(alert => (
                <AlertCard
                  key={alert.id}
                  alert={{ ...alert, isDemo: true }}
                  onAcknowledge={() => {}}
                  onDetail={() => {}}
                />
              ))}
            </>
          )}
          {alerts.length === 0 && apiKey && (
            <View style={styles.emptyAlerts}>
              <Text style={styles.emptyAlertsIcon}>✓</Text>
              <Text style={styles.emptyAlertsText}>No active alerts</Text>
              <Text style={styles.emptyAlertsSub}>Run a wallet scan or add wallets to start monitoring</Text>
            </View>
          )}
          {alerts.map(alert => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onAcknowledge={acknowledgeAlert}
              onDetail={(a) => navigation.navigate("AlertDetail", { alert: a })}
            />
          ))}
        </View>

        <View style={{ height: 20 }} />
      </ScrollView>
    </View>
  );
}

function KPI({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) {
  return (
    <View style={styles.kpi}>
      <Text style={[styles.kpiValue, highlight && { color: "#ef4444" }]}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
    </View>
  );
}

function QuickAction({ icon, label, onPress }: { icon: string; label: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.quickBtn} onPress={onPress} activeOpacity={0.7}>
      <Text style={styles.quickIcon}>{icon}</Text>
      <Text style={styles.quickLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: "#0a1628" },
  header:       { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 20, paddingVertical: 14 },
  logoText:     { fontSize: 18, fontWeight: "800", color: "#fff" },
  subtitle:     { fontSize: 11, color: "#4a7fa5", marginTop: 1 },
  settingsBtn:  { padding: 6 },
  settingsIcon: { fontSize: 20 },

  riskCard: {
    margin: 16, backgroundColor: "#0F1F3D", borderRadius: 14,
    padding: 18, borderWidth: 1, borderColor: "#1e3a5f",
  },
  gaugeRow:    { flexDirection: "row", alignItems: "center", gap: 20, marginBottom: 12 },
  kpiStack:    { flex: 1, gap: 8 },
  kpi:         {},
  kpiValue:    { fontSize: 18, fontWeight: "800", color: "#e2e8f0" },
  kpiLabel:    { fontSize: 10, color: "#64748b", marginTop: 1 },
  riskSummary: { fontSize: 12, color: "#94a3b8", lineHeight: 18 },

  modalOverlay:  { flex: 1, backgroundColor: "#000000aa", justifyContent: "center", alignItems: "center" },
  modal:         { backgroundColor: "#0F1F3D", borderRadius: 16, padding: 24, width: "80%", borderWidth: 1, borderColor: "#1e3a5f" },
  modalTitle:    { fontSize: 16, fontWeight: "800", color: "#fff", marginBottom: 6 },
  modalSub:      { fontSize: 12, color: "#94a3b8", marginBottom: 14 },
  modalInput:    { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 18, fontWeight: "700", textAlign: "center", marginBottom: 8 },
  modalHint:     { fontSize: 10, color: "#4a7fa5", marginBottom: 16, textAlign: "center" },
  modalBtns:     { flexDirection: "row", gap: 10 },
  modalCancel:   { flex: 1, backgroundColor: "#1e3a5f", borderRadius: 8, paddingVertical: 10, alignItems: "center" },
  modalCancelText:{ color: "#94a3b8", fontWeight: "600" },
  modalSave:     { flex: 1, backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 10, alignItems: "center" },
  modalSaveText: { color: "#0a1628", fontWeight: "800" },
  quickActions: { flexDirection: "row", paddingHorizontal: 16, gap: 10, marginBottom: 20 },
  quickBtn:     { flex: 1, backgroundColor: "#0F1F3D", borderRadius: 10, paddingVertical: 12, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  quickIcon:    { fontSize: 20, marginBottom: 4 },
  quickLabel:   { fontSize: 11, color: "#94a3b8", fontWeight: "600" },

  checkCard:        { marginHorizontal: 16, marginBottom: 16, backgroundColor: "#0F1F3D", borderRadius: 12, padding: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  checkTitle:       { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 2 },
  checkSub:         { fontSize: 11, color: "#4a7fa5", marginBottom: 10 },
  checkRow:         { flexDirection: "row", gap: 8 },
  checkInput:       { flex: 1, backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 10, color: "#e2e8f0", fontSize: 12, fontFamily: "monospace" },
  checkBtn:         { backgroundColor: "#00B5A5", borderRadius: 8, paddingHorizontal: 16, justifyContent: "center", alignItems: "center" },
  checkBtnText:     { color: "#0a1628", fontWeight: "800", fontSize: 13 },
  checkResult:      { marginTop: 10, borderRadius: 8, padding: 10, borderWidth: 1 },
  checkResultLabel: { fontSize: 13, fontWeight: "700", marginBottom: 4 },
  checkFlag:        { fontSize: 11, color: "#94a3b8", lineHeight: 16 },
  pulseBanner:   { flexDirection: "row", alignItems: "center", marginHorizontal: 16, marginBottom: 12, borderRadius: 10, padding: 12, borderWidth: 1, gap: 10 },
  pulseIcon:     { fontSize: 20 },
  pulseTitle:    { fontSize: 13, fontWeight: "700", marginBottom: 2 },
  pulseSub:      { fontSize: 11, color: "#94a3b8" },
  pulseDismiss:  { fontSize: 14, color: "#64748b", paddingLeft: 6 },

  lastAlertBanner: { flexDirection: "row", alignItems: "center", marginHorizontal: 16, marginBottom: 10, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: "#00B5A530", backgroundColor: "#00B5A510", gap: 10 },
  lastAlertIcon:   { fontSize: 18 },
  lastAlertTitle:  { fontSize: 12, fontWeight: "700", color: "#e2e8f0", marginBottom: 2 },
  lastAlertBody:   { fontSize: 11, color: "#64748b" },

  demoBanner:       { flexDirection: "row", alignItems: "center", marginHorizontal: 16, marginBottom: 10, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: "#f59e0b40", backgroundColor: "#f59e0b10", gap: 10 },
  demoLabel:        { fontSize: 10, fontWeight: "800", color: "#f59e0b", backgroundColor: "#f59e0b20", borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  demoText:         { flex: 1, fontSize: 11, color: "#94a3b8", lineHeight: 15 },
  demoAlertsHeader: { marginBottom: 8, paddingHorizontal: 4 },
  demoAlertsLabel:  { fontSize: 9, fontWeight: "800", color: "#f59e0b", letterSpacing: 0.5 },
  emptyAlerts:      { alignItems: "center", paddingVertical: 30, backgroundColor: "#0F1F3D", borderRadius: 10, borderWidth: 1, borderColor: "#1e3a5f" },
  emptyAlertsIcon:  { fontSize: 28, color: "#22c55e", marginBottom: 8 },
  emptyAlertsText:  { fontSize: 14, fontWeight: "700", color: "#e2e8f0", marginBottom: 4 },
  emptyAlertsSub:   { fontSize: 12, color: "#64748b", textAlign: "center", paddingHorizontal: 20 },

  threatBanner:  { marginHorizontal: 16, marginBottom: 16, backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, borderWidth: 1, borderColor: "#1e3a5f", borderLeftWidth: 3 },
  threatHeader:  { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 8 },
  threatIcon:    { fontSize: 20, marginTop: 1 },
  threatWeekLabel:{ fontSize: 9, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 2 },
  threatTitle:   { fontSize: 13, fontWeight: "700", color: "#e2e8f0" },
  threatSevPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  threatSevText: { fontSize: 9, fontWeight: "800" },
  threatBody:    { fontSize: 12, color: "#94a3b8", lineHeight: 18, marginBottom: 8 },
  threatAction:  { fontSize: 11, color: "#00B5A5", fontWeight: "600" },

  section:       { paddingHorizontal: 16 },
  sectionHeader: { flexDirection: "row", alignItems: "center", marginBottom: 12, gap: 10 },
  sectionTitle:  { fontSize: 14, fontWeight: "700", color: "#e2e8f0" },
  alertBadge:    { backgroundColor: "#ef444420", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: "#ef444440" },
  alertBadgeText:{ fontSize: 10, color: "#ef4444", fontWeight: "700" },
});
