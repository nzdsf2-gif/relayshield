import React, { useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  ScrollView, KeyboardAvoidingView, Platform, Linking,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as SecureStore from "expo-secure-store";
import * as RS from "../api/relayshield";
import { connectSolanaWallet } from "../utils/mwa";
import { getInstallId } from "../utils/installId";
import { track } from "../utils/analytics";
import { ExposureCard } from "../components/ExposureCard";

const WALLETS_KEY = "cs_wallets";
const EMAILS_KEY  = "cs_monitored_emails";
const PHONE_KEY   = "cs_phone_number";
const APIKEY_KEY  = "cs_api_key";
const ONBOARDED   = "cs_onboarded";

type Chain = "solana" | "evm" | "bitcoin" | "ton";
const CHAIN_LABELS: Record<Chain, string> = {
  solana:  "◎ Solana",
  evm:     "Ξ EVM",
  bitcoin: "₿ Bitcoin",
  ton:     "💎 TON",
};

const CHAIN_TIPS: Record<Chain, { icon: string; tip: string }[]> = {
  solana: [
    { icon: "🧲", tip: "Address poisoning is rampant on Solana. Attackers send dust from addresses that share your first and last characters. Never copy an address from transaction history." },
    { icon: "🪙", tip: "Solana token approvals are implicit. Any program you interact with may retain delegated access to your tokens. Sweep approvals regularly." },
    { icon: "🔍", tip: "Scan any token before buying. Rug-pulls and honeypots on Solana often have transfer restrictions hidden in the contract that prevent selling." },
  ],
  evm: [
    { icon: "🔓", tip: "EVM token approvals are permanent until revoked. Forgotten unlimited approvals granted months ago are still active — a single exploited spender can drain your wallet." },
    { icon: "🪤", tip: "Signature poisoning targets MetaMask and WalletConnect users. What is displayed in the signing popup and what is actually being signed can differ." },
    { icon: "📋", tip: "Clipboard malware silently replaces EVM addresses you copy. Always verify the last 6 characters of a destination address before confirming." },
  ],
  bitcoin: [
    { icon: "📋", tip: "Bitcoin clipboard malware is widespread. Malware monitors your clipboard and replaces any Bitcoin address you copy with an attacker's address. Verify the full address before sending — there is no undo." },
    { icon: "🔤", tip: "Legacy (1...), SegWit (3...), and native SegWit (bc1q...) addresses are not always interchangeable. Confirm address format compatibility with the receiving platform before sending." },
    { icon: "🔒", tip: "Never share your xpub (extended public key). It exposes your entire transaction history and all future addresses, even without your private key." },
  ],
  ton: [
    { icon: "🔄", tip: "TON has two address forms — bounceable (EQ...) and non-bounceable (UQ...). Smart contracts typically require bounceable; wallets use non-bounceable. Sending to the wrong type can result in lost funds." },
    { icon: "🔍", tip: "TON smart contract source verification is rare. Most TON DeFi contracts are unaudited. Check contract reputation before depositing or approving any interaction." },
    { icon: "💬", tip: "TON is deeply integrated with Telegram. Scam bots and fake wallet apps targeting TON users are common in Telegram groups — verify any app or contract address independently before use." },
  ],
};

interface Props { onComplete: (opts?: { openPaywall?: boolean }) => void; }

export function OnboardingScreen({ onComplete }: Props) {
  const insets = useSafeAreaInsets();
  const [step, setStep]         = useState(0);
  const [walletAddr, setWalletAddr] = useState("");
  const [walletLabel, setWalletLabel] = useState("Main Wallet");
  const [walletChain, setWalletChain] = useState<Chain>("solana");
  const [email, setEmail]       = useState("");
  const [phone, setPhone]       = useState("");
  const [apiKey, setApiKey]     = useState("");
  const [error, setError]       = useState("");

  // Crypto Shield Pro subscribers get their RelayShield API key
  // auto-provisioned, tied to their subscription — no separate signup, no
  // separate charge. This was built 2026-07-11 (SettingsScreen.tsx's
  // "Unlock Live Scans") but never ported into onboarding, so every new or
  // reinstalling subscriber only ever saw the old manual-paste-or-go-
  // sign-up-separately flow below and never discovered the real mechanism.
  // FIRST-RUN VALUE, before anything is asked for. Both of these used to be
  // behind a key or a manual paste: a new user typed a 44-character address and
  // was shown nothing, and the email step said "this unlocks once your
  // subscription is linked". Now a connected wallet is scanned immediately and
  // the email can be checked once for free. Neither needs an account.
  const [connecting, setConnecting] = useState(false);
  const [scanning,   setScanning]   = useState(false);
  const [scan, setScan] = useState<{ level: string; flags: string[]; failed?: string } | null>(null);
  const [exposure, setExposure]     = useState<RS.FreeExposureResult | null>(null);
  const [checkingEmail, setCheckingEmail] = useState(false);
  const [exposureError, setExposureError] = useState("");
  const [linkEmail, setLinkEmail] = useState("");
  const [linking,   setLinking]   = useState(false);
  const [linkError, setLinkError] = useState("");

  async function handleUnlockSubscription() {
    const trimmed = linkEmail.trim();
    if (!trimmed || !trimmed.includes("@")) {
      setLinkError("Enter the email you used at checkout.");
      return;
    }
    setLinking(true);
    setLinkError("");
    try {
      const key = await RS.linkCryptoShieldSubscription(trimmed);
      setApiKey(key);
    } catch (err: any) {
      setLinkError(err?.message ?? "Could not find a subscription for that email.");
    }
    setLinking(false);
  }

  const SCORE_MAP: Record<string, number> = { LOW: 20, MEDIUM: 45, HIGH: 70, CRITICAL: 90 };

  // Scan the address now, with NO key: /v1/wallet-risk is keyless (capped per
  // source IP), so the free tier's one wallet can actually be scanned.
  async function runFirstScan(address: string) {
    const addr = address.trim();
    if (!addr) return;
    setScanning(true); setScan(null); setError("");
    try {
      const d: any = await RS.scanWalletRisk(addr, null);
      const level = String(d?.risk_level ?? "LOW").toUpperCase();
      const flags = Array.isArray(d?.risk_flags)
        ? d.risk_flags.slice(0, 3).map((f: any) => (typeof f === "string" ? f : String(f?.label ?? f?.name ?? ""))).filter(Boolean)
        : [];
      setScan({ level, flags });
    } catch (e: any) {
      setScan({ level: "", flags: [], failed: e?.message ?? "Couldn't scan this wallet. You can try again from the Wallets tab." });
    }
    setScanning(false);
  }

  async function handleConnectWallet() {
    setConnecting(true); setError("");
    try {
      const addr = await connectSolanaWallet();
      setWalletChain("solana");
      setWalletAddr(addr);
      track("wallet_connected", "ok");
      setConnecting(false);
      await runFirstScan(addr);
      return;
    } catch (e: any) {
      track("wallet_connected", "failed");
      setError(e?.message ?? "Couldn't connect to a wallet app. Make sure Phantom or Solflare is installed, or paste the address below.");
    }
    setConnecting(false);
  }

  async function runFreeEmailCheck() {
    const addr = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)) {
      setExposureError("Enter an email address, e.g. you@example.com.");
      return;
    }
    setCheckingEmail(true); setExposure(null); setExposureError("");
    try {
      setExposure(await RS.freeExposureCheck(addr, await getInstallId()));
    } catch (e: any) {
      setExposureError(e?.message ?? "Couldn't run the check. Check your connection and try again.");
    }
    setCheckingEmail(false);
  }

  async function finish(opts?: { openPaywall?: boolean }) {
    // Persist whatever the user filled in. A wallet that was scanned above keeps
    // its result, so the Dashboard shows it instead of "not scanned yet".
    const wallets = walletAddr.trim()
      ? [{
          address: walletAddr.trim(), label: walletLabel || "Main Wallet", chain: walletChain,
          addedAt: new Date().toISOString(),
          ...(scan && scan.level && !scan.failed
            ? { lastRiskScore: SCORE_MAP[scan.level] ?? 20, lastRiskLevel: scan.level, lastChecked: new Date().toISOString() }
            : {}),
        }]
      : [];
    const emails = email.trim() && email.includes("@") ? [email.trim().toLowerCase()] : [];

    await Promise.all([
      SecureStore.setItemAsync(WALLETS_KEY, JSON.stringify(wallets)),
      SecureStore.setItemAsync(EMAILS_KEY,  JSON.stringify(emails)),
      phone.trim() ? SecureStore.setItemAsync(PHONE_KEY, phone.trim()) : Promise.resolve(),
      apiKey.trim() ? SecureStore.setItemAsync(APIKEY_KEY, apiKey.trim()) : Promise.resolve(),
      SecureStore.setItemAsync(ONBOARDED, "true"),
    ]);
    track("onboarding_completed", [
      walletAddr.trim() ? "wallet" : "nowallet",
      exposure && !exposure.already_used ? "check" : "nocheck",
    ].join("_"));
    onComplete(opts);
  }

  function next() { setError(""); setStep(s => s + 1); }
  function back() { setError(""); setStep(s => s - 1); }

  const TOTAL = 5;
  const pct   = ((step + 1) / TOTAL) * 100;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={[styles.container, { paddingTop: insets.top + 10 }]}>

        {/* Progress bar */}
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${pct}%` as any }]} />
        </View>

        <ScrollView showsVerticalScrollIndicator={false} style={{ flex: 1 }}>

          {/* ── Step 0: Welcome ── */}
          {step === 0 && (
            <View style={styles.stepWrap}>
              <Text style={styles.logo}>🛡</Text>
              <Text style={styles.heroTitle}>Crypto Shield</Text>
              <Text style={styles.heroSub}>by RelayShield</Text>
              <Text style={styles.heroTagline}>
                The only wallet security app that watches your credentials, not just your chain.
              </Text>
              <Text style={styles.heroBody}>
                Real-time security monitoring for your Solana, EVM, Bitcoin, and TON wallets. Flags
                high-risk tokens, detects address poisoning, monitors threats from criminal Telegram
                channels, and alerts you before attackers strike.
              </Text>

              <View style={styles.trustStrip}>
                {[
                  ["🔒", "We never ask for your seed phrase or private keys — read-only monitoring only, we can't move your funds."],
                  ["🛡", "Every alert is cryptographically verified before it reaches your phone."],
                  ["📋", "RelayShield carries active Tech E&O and Cyber Insurance coverage."],
                ].map(([icon, text]) => (
                  <View key={text} style={styles.trustRow}>
                    <Text style={styles.trustIcon}>{icon}</Text>
                    <Text style={styles.trustText}>{text}</Text>
                  </View>
                ))}
              </View>

              <View style={styles.featureList}>
                {[
                  ["🔍", "Token risk scanning"],
                  ["🧲", "Address poisoning detection"],
                  ["📡", "Live IOC feed — phishing, C2, drainers"],
                  ["🔐", "Security sweep — breach + infostealer"],
                  ["📊", "Vendor supply chain monitoring"],
                ].map(([icon, text]) => (
                  <View key={text} style={styles.featureRow}>
                    <Text style={styles.featureIcon}>{icon}</Text>
                    <Text style={styles.featureText}>{text}</Text>
                  </View>
                ))}
              </View>

              <Text style={styles.noAccount}>No account required to get started.</Text>
            </View>
          )}

          {/* ── Step 1: Add wallet ── */}
          {step === 1 && (
            <View style={styles.stepWrap}>
              <Text style={styles.stepNum}>1 of 4</Text>
              <Text style={styles.stepTitle}>Add your wallet</Text>
              <Text style={styles.stepDesc}>
                Crypto Shield monitors your wallet for high-risk tokens, flagged counterparties, and
                address poisoning attacks. You can add more wallets after setup.
              </Text>

              <TouchableOpacity
                style={[styles.connectBtn, (connecting || scanning) && { opacity: 0.6 }]}
                onPress={handleConnectWallet}
                disabled={connecting || scanning}
              >
                <Text style={styles.connectBtnText}>
                  {connecting ? "Opening your wallet app…" : "◎ Connect Phantom or Solflare"}
                </Text>
              </TouchableOpacity>
              <Text style={styles.skipHint}>
                Read-only. We only see your public address; your wallet app keeps your keys and we never ask for them.
              </Text>

              <Text style={[styles.fieldLabel, { marginTop: 14 }]}>Or choose a chain and paste an address</Text>
              <View style={styles.chainRow}>
                {(["solana", "evm", "bitcoin", "ton"] as Chain[]).map(c => (
                  <TouchableOpacity
                    key={c}
                    style={[styles.chainBtn, walletChain === c && styles.chainBtnActive]}
                    onPress={() => setWalletChain(c)}
                  >
                    <Text style={[styles.chainBtnText, walletChain === c && { color: "#00B5A5" }]}>
                      {CHAIN_LABELS[c]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.fieldLabel}>Wallet Address</Text>
              <TextInput
                style={styles.input}
                value={walletAddr}
                onChangeText={(t) => { setWalletAddr(t); setScan(null); }}
                placeholder={
                  walletChain === "solana"  ? "e.g. 7xKXtg2CW87d..." :
                  walletChain === "evm"     ? "e.g. 0x742d35Cc66..." :
                  walletChain === "bitcoin" ? "e.g. bc1q..." :
                                              "e.g. EQBv..."
                }
                placeholderTextColor="#334155"
                autoCapitalize="none"
                autoCorrect={false}
              />

              {!!walletAddr.trim() && !scan && !scanning && (
                <TouchableOpacity style={styles.scanNowBtn} onPress={() => runFirstScan(walletAddr)}>
                  <Text style={styles.scanNowText}>Scan this wallet now (free)</Text>
                </TouchableOpacity>
              )}
              {scanning && <Text style={styles.scanLine}>Scanning…</Text>}
              {scan && !scan.failed && (
                <View style={[styles.scanCard, { borderColor: scan.level === "LOW" ? "#38bdf8" : scan.level === "MEDIUM" ? "#facc15" : "#ef4444" }]}>
                  <Text style={styles.scanCardTitle}>
                    {scan.level === "LOW" ? "No known risk flags on this wallet" : `Risk level: ${scan.level}`}
                  </Text>
                  {scan.flags.map((f, i) => <Text key={i} style={styles.scanLine}>• {f}</Text>)}
                  <Text style={styles.scanLine}>
                    {scan.level === "LOW"
                      ? "That's what our sources know today, not a guarantee. Wallets can be drained by a signature you approve."
                      : "Don't send funds to or approve anything from this wallet until you've looked into it."}
                  </Text>
                </View>
              )}
              {scan?.failed ? <Text style={styles.errorText}>{scan.failed}</Text> : null}

              <Text style={styles.fieldLabel}>Label (optional)</Text>
              <TextInput
                style={styles.input}
                value={walletLabel}
                onChangeText={setWalletLabel}
                placeholder="e.g. Main Wallet"
                placeholderTextColor="#334155"
              />

              {error ? <Text style={styles.errorText}>{error}</Text> : null}

              <View style={styles.tipsBox}>
                <Text style={styles.tipsTitle}>Security tips for {CHAIN_LABELS[walletChain]} users</Text>
                {CHAIN_TIPS[walletChain].map((t, i) => (
                  <View key={i} style={styles.tipRow}>
                    <Text style={styles.tipIcon}>{t.icon}</Text>
                    <Text style={styles.tipText}>{t.tip}</Text>
                  </View>
                ))}
              </View>

              <Text style={styles.skipHint}>You can skip this and add a wallet later from the Wallets tab.</Text>
            </View>
          )}

          {/* ── Step 2: Email ── */}
          {step === 2 && (
            <View style={styles.stepWrap}>
              <Text style={styles.stepNum}>2 of 4</Text>
              <Text style={styles.stepTitle}>Monitor your email</Text>
              <Text style={styles.stepDesc}>
                Credential theft is one of the main ways wallets get drained, and it starts with an
                email that is already in a leak. Check yours now: your first check is free, no
                subscription needed. Ongoing monitoring is part of the 7-day free trial.
              </Text>

              <Text style={styles.fieldLabel}>Email Address (optional)</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                placeholder="you@gmail.com"
                placeholderTextColor="#334155"
                autoCapitalize="none"
                keyboardType="email-address"
                autoCorrect={false}
              />
              <Text style={styles.skipHint}>Optional — skip if you prefer to add later in Settings.</Text>

              {!exposure && (
                <TouchableOpacity
                  style={[styles.scanNowBtn, checkingEmail && { opacity: 0.6 }]}
                  onPress={runFreeEmailCheck}
                  disabled={checkingEmail}
                >
                  <Text style={styles.scanNowText}>{checkingEmail ? "Checking…" : "Check this email now (free)"}</Text>
                </TouchableOpacity>
              )}
              {!!exposureError && <Text style={styles.errorText}>{exposureError}</Text>}
              {exposure && (
                <ExposureCard
                  result={exposure}
                  onRetry={runFreeEmailCheck}
                  onUpgrade={() => finish({ openPaywall: true })}
                />
              )}
            </View>
          )}

          {/* ── Step 3: Phone ── */}
          {step === 3 && (
            <View style={styles.stepWrap}>
              <Text style={styles.stepNum}>3 of 4</Text>
              {/* CSM-SIMSWAP-1. THE WORST OF THE FOUR, BECAUSE IT IS THE
                  PRIMARY ONBOARDING FLOW: it said "to enable monitoring" and
                  nothing was enabled. checkSimSwap() has zero callers and the
                  number never leaves the device.

                  The threat education is TRUE and stays. What changed is the
                  promise: the step now points at the SIM-lock guide, which is
                  built (components/SimLockGuide.tsx), real, carrier by carrier,
                  and is the single most effective thing a user can do about
                  this anyway -- a carrier port-out lock prevents the swap,
                  where monitoring only tells you afterwards. So the honest
                  version of this screen is also the more useful one. */}
              <Text style={styles.stepTitle}>SIM swap: lock your number</Text>
              <Text style={styles.stepDesc}>
                SIM swaps are the #1 method attackers use to bypass exchange 2FA and drain crypto
                accounts. The strongest defence is a port-out lock with your carrier, and Crypto
                Shield shows you how to set one up. Enter the number you use for exchange logins; it
                stays on this device until you choose to turn on SIM swap monitoring in Settings.
              </Text>

              <Text style={styles.fieldLabel}>Phone Number (optional)</Text>
              <TextInput
                style={styles.input}
                value={phone}
                onChangeText={setPhone}
                placeholder="+12125551234  (include country code)"
                placeholderTextColor="#334155"
                keyboardType="phone-pad"
                autoCorrect={false}
              />
              <Text style={styles.skipHint}>
                Must be in E.164 format. Cannot be read automatically — mobile OS does not expose the
                device phone number to apps.
              </Text>
            </View>
          )}

          {/* ── Step 4: Unlock subscription + other products ── */}
          {step === 4 && (
            <View style={styles.stepWrap}>
              <Text style={styles.stepNum}>4 of 4</Text>
              <Text style={styles.stepTitle}>Enhanced monitoring</Text>
              <Text style={styles.stepDesc}>
                Crypto Shield works out of the box — wallet scanning, live threat intel, and address
                poisoning detection require no account. Breach monitoring, infostealer checks, and
                vendor supply chain analysis are already included in your subscription.
              </Text>

              <Text style={styles.fieldLabel}>Unlock Live Scans</Text>
              <Text style={styles.skipHint}>
                Already subscribed to Crypto Shield Pro? Enter the email you used at checkout — live
                scans are already included in your subscription, no extra charge and no separate signup.
              </Text>
              <TextInput
                style={[styles.input, { marginTop: 10 }]}
                value={linkEmail}
                onChangeText={(t) => { setLinkEmail(t); setLinkError(""); }}
                placeholder="you@example.com"
                placeholderTextColor="#334155"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
              />
              {!!linkError && (
                <Text style={{ fontSize: 11, color: "#ef4444", marginBottom: 8, marginTop: -6 }}>{linkError}</Text>
              )}
              {apiKey ? (
                <Text style={{ fontSize: 12, color: "#00B5A5", marginBottom: 4, fontWeight: "600" }}>✓ Subscription unlocked</Text>
              ) : (
                <TouchableOpacity style={styles.nextBtn} onPress={handleUnlockSubscription} disabled={linking}>
                  <Text style={styles.nextBtnText}>{linking ? "Checking…" : "Unlock My Subscription"}</Text>
                </TouchableOpacity>
              )}

              <View style={styles.divider} />

              <Text style={styles.otherTitle}>Other RelayShield products</Text>
              <View style={styles.discountBanner}>
                <Text style={styles.discountBannerText}>
                  As a Crypto Shield Mobile subscriber, get 10% off your first payment on any RelayShield solution below — use code <Text style={styles.discountCode}>CSMOBILE10</Text> at checkout.
                </Text>
              </View>
              {[
                {
                  label: "Business Starter / Business Basic — Identity Security via WhatsApp & Telegram",
                  desc: "Always-on identity security for SMB teams. Carrier-layer SIM swap detection, credential breach monitoring, infostealer log alerts, domain lookalike detection, session exposure, OAuth app monitoring, and coordinated attack chain warnings — delivered as a message to WhatsApp or Telegram before you know something's wrong.",
                  url: "https://relayshield.net",
                },
                {
                  label: "Multi-Site Shield — Identity Monitoring for Multi-Location Businesses",
                  desc: "Per-location risk dashboards with cumulative portfolio-level incident monitoring, location drill-down views, and cross-location breach correlation (same credential at Location 3 and Location 7 — flagged). Automatic PSA ticket creation in ConnectWise and Autotask on every CRITICAL alert. Built for franchise operators, multi-site SMBs, and the MSPs who manage them.",
                  url: "https://relayshield.net/msp",
                },
                {
                  label: "Threat Intelligence IOC Engine — for Enterprise NOC/SOC, MSPs, and MSSPs",
                  desc: "Threat intelligence and IOC API engine for security operations teams. Live dark channel pipeline monitoring criminal Telegram channels for credential dumps, phishing infrastructure, C2 addresses, and wallet drainer contracts. CISA KEV vulnerability alerts, actor profiling, STIX/TAXII 2.1 export, and REST API access to the full corpus. Powers the Intel feed in this app.",
                  url: "https://relayshield.net/ti",
                },
                {
                  label: "Developer API",
                  desc: "REST API for identity risk scoring, IOC lookup, breach and infostealer checks, SIM swap monitoring, domain lookalike detection, and wallet risk. Metered and subscription tiers. Integrate RelayShield signals into your own security tooling.",
                  url: "https://api.relayshield.net/developers",
                },
              ].map(p => (
                <TouchableOpacity key={p.label} style={styles.productCard} onPress={() => Linking.openURL(p.url)}>
                  <Text style={styles.productLabel}>{p.label} →</Text>
                  <Text style={styles.productDesc}>{p.desc}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

        </ScrollView>

        {/* Nav buttons */}
        <View style={[styles.navRow, { paddingBottom: insets.bottom + 10 }]}>
          {step > 0 && (
            <TouchableOpacity style={styles.backBtn} onPress={back}>
              <Text style={styles.backBtnText}>← Back</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={[styles.nextBtn, step === 0 && { flex: 1 }]}
            onPress={step === TOTAL - 1 ? () => finish() : next}
          >
            <Text style={styles.nextBtnText}>
              {step === 0 ? "Get Started" : step === TOTAL - 1 ? "Start Monitoring →" : "Next →"}
            </Text>
          </TouchableOpacity>
        </View>
        {step === 0 && (
          <Text style={styles.consentText}>
            By continuing, you agree to our{" "}
            <Text style={styles.consentLink} onPress={() => Linking.openURL("https://terms.relayshield.net")}>Terms of Service</Text>
            {" "}and{" "}
            <Text style={styles.consentLink} onPress={() => Linking.openURL("https://privacy.relayshield.net")}>Privacy Policy</Text>.
          </Text>
        )}

      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container:     { flex: 1, backgroundColor: "#0a1628" },
  progressTrack: { height: 3, backgroundColor: "#1e3a5f", marginHorizontal: 20, borderRadius: 2, marginBottom: 20 },
  progressFill:  { height: 3, backgroundColor: "#00B5A5", borderRadius: 2 },

  stepWrap:    { paddingHorizontal: 24, paddingBottom: 20 },
  stepNum:     { fontSize: 11, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase" },
  stepTitle:   { fontSize: 24, fontWeight: "800", color: "#e2e8f0", marginBottom: 10, lineHeight: 30 },
  stepDesc:    { fontSize: 13, color: "#94a3b8", lineHeight: 20, marginBottom: 22 },
  fieldLabel:  { fontSize: 10, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 6 },
  input:       { backgroundColor: "#0F1F3D", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 10, padding: 13, color: "#e2e8f0", fontSize: 13, marginBottom: 16, fontFamily: "monospace" },
  connectBtn:     { backgroundColor: "#00B5A5", borderRadius: 12, paddingVertical: 14, alignItems: "center", marginBottom: 6 },
  connectBtnText: { color: "#0a1628", fontWeight: "800", fontSize: 14 },
  scanNowBtn:     { borderWidth: 1, borderColor: "#00B5A5", borderRadius: 10, paddingVertical: 11, alignItems: "center", marginBottom: 12 },
  scanNowText:    { color: "#00B5A5", fontWeight: "700", fontSize: 13 },
  scanCard:       { backgroundColor: "#0F1F3D", borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 14 },
  scanCardTitle:  { color: "#e2e8f0", fontWeight: "800", fontSize: 14, marginBottom: 6 },
  scanLine:       { color: "#94a3b8", fontSize: 12.5, lineHeight: 18, marginBottom: 6 },
  chainRow:    { flexDirection: "row", gap: 8, marginBottom: 18 },
  chainBtn:    { flex: 1, backgroundColor: "#0F1F3D", borderRadius: 8, paddingVertical: 9, alignItems: "center", borderWidth: 1, borderColor: "#1e3a5f" },
  chainBtnActive: { borderColor: "#00B5A5", backgroundColor: "#00B5A510" },
  chainBtnText: { fontSize: 11, color: "#64748b", fontWeight: "600" },
  skipHint:    { fontSize: 11, color: "#4a7fa5", lineHeight: 16, fontStyle: "italic" },
  tipsBox:     { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  tipsTitle:   { fontSize: 10, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 10 },
  tipRow:      { flexDirection: "row", gap: 10, marginBottom: 10, alignItems: "flex-start" },
  tipIcon:     { fontSize: 15, width: 22, marginTop: 1 },
  tipText:     { fontSize: 12, color: "#94a3b8", flex: 1, lineHeight: 17 },
  errorText:   { fontSize: 12, color: "#ef4444", marginBottom: 8 },

  logo:        { fontSize: 56, textAlign: "center", marginTop: 20, marginBottom: 12 },
  heroTitle:   { fontSize: 30, fontWeight: "900", color: "#e2e8f0", textAlign: "center", marginBottom: 4 },
  heroSub:     { fontSize: 13, color: "#00B5A5", textAlign: "center", marginBottom: 22, fontWeight: "600" },
  heroTagline: { fontSize: 14, color: "#e2e8f0", fontWeight: "700", textAlign: "center", lineHeight: 20, marginBottom: 16 },
  heroBody:    { fontSize: 13, color: "#94a3b8", lineHeight: 20, textAlign: "center", marginBottom: 28 },
  trustStrip:  { backgroundColor: "#00B5A50d", borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: "#00B5A530" },
  trustRow:    { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 10 },
  trustIcon:   { fontSize: 15, width: 22, marginTop: 1 },
  trustText:   { fontSize: 12, color: "#94a3b8", flex: 1, lineHeight: 17 },
  featureList: { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 16, marginBottom: 20, borderWidth: 1, borderColor: "#1e3a5f" },
  featureRow:  { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 12 },
  featureIcon: { fontSize: 18, width: 26 },
  featureText: { fontSize: 13, color: "#e2e8f0", flex: 1, lineHeight: 18 },
  noAccount:   { fontSize: 12, color: "#4a7fa5", textAlign: "center", fontStyle: "italic" },

  linkBtn:     { borderWidth: 1, borderColor: "#00B5A540", borderRadius: 8, paddingVertical: 10, alignItems: "center", marginBottom: 4 },
  linkBtnText: { fontSize: 13, color: "#00B5A5", fontWeight: "600" },
  divider:     { height: 1, backgroundColor: "#1e3a5f", marginVertical: 20 },
  otherTitle:  { fontSize: 11, color: "#4a7fa5", fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 12 },
  discountBanner:     { backgroundColor: "#00B5A512", borderRadius: 10, padding: 12, marginBottom: 14, borderWidth: 1, borderColor: "#00B5A540" },
  discountBannerText: { fontSize: 12, color: "#94a3b8", lineHeight: 17 },
  discountCode:        { color: "#00B5A5", fontWeight: "800" },
  productCard: { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: "#1e3a5f" },
  productLabel:{ fontSize: 13, fontWeight: "700", color: "#00B5A5", marginBottom: 4 },
  productDesc: { fontSize: 12, color: "#64748b", lineHeight: 17 },

  consentText: { fontSize: 10, color: "#334155", textAlign: "center", paddingHorizontal: 20, paddingTop: 8, paddingBottom: 4, lineHeight: 15 },
  consentLink: { color: "#4a7fa5", textDecorationLine: "underline" as const },
  navRow:      { flexDirection: "row", paddingHorizontal: 20, paddingTop: 12, gap: 10, borderTopWidth: 1, borderTopColor: "#1e3a5f" },
  backBtn:     { flex: 1, borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 12, paddingVertical: 14, alignItems: "center" },
  backBtnText: { color: "#64748b", fontWeight: "600", fontSize: 14 },
  nextBtn:     { flex: 2, backgroundColor: "#00B5A5", borderRadius: 12, paddingVertical: 14, alignItems: "center" },
  nextBtnText: { color: "#0a1628", fontWeight: "800", fontSize: 15 },
});
