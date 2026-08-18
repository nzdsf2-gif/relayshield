import React, { useState, useEffect } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  ScrollView, Alert, Switch, Linking, Modal, ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import { useWallets } from "../hooks/useWallet";
import * as SecureStore from "expo-secure-store";
import * as RS from "../api/relayshield";
import { useNFTCollections, NFT_CHAINS, type NFTChain } from "../hooks/useNFTCollections";
import Constants from "expo-constants";
import { useUpdateCheck } from "../hooks/useUpdateCheck";

const EMAILS_STORE = "cs_monitored_emails";
const MAX_EMAILS   = 3;

function EmailManager() {
  const [slots, setSlots] = useState<string[]>(["", "", ""]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(EMAILS_STORE).then(v => {
      if (v) {
        const stored = JSON.parse(v) as string[];
        setSlots([stored[0] || "", stored[1] || "", stored[2] || ""]);
      }
    });
  }, []);

  async function saveEmails() {
    const valid = slots.map(s => s.trim().toLowerCase()).filter(s => s.includes("@"));
    await SecureStore.setItemAsync(EMAILS_STORE, JSON.stringify(valid));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <View>
      {[0, 1, 2].map(i => (
        <View key={i} style={{ marginBottom: 10 }}>
          <Text style={em.slotLabel}>Email {i + 1}</Text>
          <TextInput
            style={em.input}
            value={slots[i]}
            onChangeText={v => { const n = [...slots]; n[i] = v; setSlots(n); }}
            placeholder={i === 0 ? "e.g. you@gmail.com" : i === 1 ? "e.g. work@company.com" : "Optional third email"}
            placeholderTextColor="#334155"
            autoCapitalize="none"
            keyboardType="email-address"
            autoCorrect={false}
          />
        </View>
      ))}
      <TouchableOpacity style={em.saveBtn} onPress={saveEmails}>
        <Text style={em.saveBtnText}>{saved ? "✓ Saved" : "Save Monitored Emails"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const em = StyleSheet.create({
  slotLabel: { fontSize: 11, color: "#e2e8f0", fontWeight: "700", letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 5 },
  input:     { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 10, color: "#e2e8f0", fontSize: 13 },
  saveBtn:   { backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 10, alignItems: "center", marginTop: 4 },
  saveBtnText: { color: "#0a1628", fontWeight: "800", fontSize: 13 },
  limitNote: { fontSize: 11, color: "#4a7fa5", marginTop: 8, fontStyle: "italic" },
});

const PHONE_STORE      = "cs_phone_number";
const PLAN_STORE       = "cs_plan_tier";
const MAX_NFT_COLLECTIONS = 10;

const CHAIN_CONFIG: Record<NFTChain, { label: string; color: string; placeholder: string; hint: string }> = {
  solana: { label: "SOL", color: "#9945FF", placeholder: "e.g. mad_lads", hint: "Magic Eden slug from magiceden.io/marketplace/{slug}" },
  eth:    { label: "ETH", color: "#627EEA", placeholder: "e.g. 0xBC4C...or boredapeyachtclub", hint: "Contract address or OpenSea collection slug" },
  base:   { label: "BASE", color: "#0052FF", placeholder: "e.g. 0x1234... or based-fellas", hint: "Contract address or OpenSea Base collection slug" },
  ton:    { label: "TON", color: "#2AABEE", placeholder: "e.g. EQC... collection address", hint: "Getgems collection address from getgems.io" },
};

function NFTCollectionManager() {
  const { collections, addCollection: addCollectionShared, removeCollection } = useNFTCollections();
  const [showModal,   setShowModal]   = useState(false);
  const [chain,       setChain]       = useState<NFTChain>("solana");
  const [input,       setInput]       = useState("");
  const [error,       setError]       = useState("");

  async function addCollection() {
    if (collections.length >= MAX_NFT_COLLECTIONS) {
      setError(`Limit reached — max ${MAX_NFT_COLLECTIONS} collections.`); return;
    }
    const result = await addCollectionShared(chain, input);
    if (!result.ok) { setError(result.error || "Could not add collection."); return; }
    setInput("");
    setError("");
    setShowModal(false);
  }

  const cfg = CHAIN_CONFIG[chain];

  return (
    <View>
      <Text style={em.limitNote}>
        Monitor floor prices across Solana, ETH, Base, and TON. Alerts fire when floor drops ≥15%. Up to {MAX_NFT_COLLECTIONS} collections ({MAX_NFT_COLLECTIONS - collections.length} remaining).
      </Text>

      {/* Collection list */}
      {collections.length > 0 ? (
        collections.map((col, i) => {
          const c = CHAIN_CONFIG[col.chain];
          if (!c) return null; // shouldn't happen post-load-time cleanup, but never crash the screen
          return (
            <View key={`${col.chain}-${col.id}-${i}`} style={nft.row}>
              <View style={[nft.chainBadge, { backgroundColor: c.color + "22", borderColor: c.color + "55" }]}>
                <Text style={[nft.chainLabel, { color: c.color }]}>{c.label}</Text>
              </View>
              <Text style={nft.idText} numberOfLines={1}>{col.id}</Text>
              <TouchableOpacity onPress={() => removeCollection(col.chain, col.id)}>
                <Text style={nft.removeBtn}>✕</Text>
              </TouchableOpacity>
            </View>
          );
        })
      ) : (
        <Text style={[em.limitNote, { fontStyle: "italic", marginBottom: 8 }]}>No collections registered yet.</Text>
      )}

      {collections.length < MAX_NFT_COLLECTIONS && (
        <TouchableOpacity style={[em.saveBtn, { marginTop: 10 }]} onPress={() => { setShowModal(true); setError(""); setInput(""); setChain("solana"); }}>
          <Text style={em.saveBtnText}>+ Add Collection</Text>
        </TouchableOpacity>
      )}

      {/* Add modal */}
      <Modal visible={showModal} transparent animationType="slide">
        <View style={nft.overlay}>
          <View style={nft.modal}>
            <Text style={nft.modalTitle}>Add NFT Collection</Text>

            {/* Chain selector */}
            <Text style={nft.modalLabel}>Chain</Text>
            <View style={nft.chainRow}>
              {NFT_CHAINS.map(ch => {
                const cc = CHAIN_CONFIG[ch];
                const active = chain === ch;
                return (
                  <TouchableOpacity
                    key={ch}
                    style={[nft.chainBtn, active && { backgroundColor: cc.color + "33", borderColor: cc.color }]}
                    onPress={() => { setChain(ch); setInput(""); setError(""); }}
                  >
                    <Text style={[nft.chainBtnText, { color: active ? cc.color : "#64748b" }]}>{cc.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* ID input */}
            <Text style={nft.modalLabel}>Collection ID</Text>
            <TextInput
              style={nft.input}
              value={input}
              onChangeText={v => { setInput(v); setError(""); }}
              placeholder={cfg.placeholder}
              placeholderTextColor="#334155"
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={addCollection}
            />
            <Text style={nft.hint}>{cfg.hint}</Text>
            {error ? <Text style={nft.error}>{error}</Text> : null}

            <View style={{ flexDirection: "row", gap: 8, marginTop: 16 }}>
              <TouchableOpacity style={[em.saveBtn, { flex: 1, backgroundColor: "#1e3a5f" }]} onPress={() => setShowModal(false)}>
                <Text style={[em.saveBtnText, { color: "#94a3b8" }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[em.saveBtn, { flex: 1 }]} onPress={addCollection}>
                <Text style={em.saveBtnText}>Add</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const nft = StyleSheet.create({
  row:        { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a", gap: 8 },
  chainBadge: { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  chainLabel: { fontSize: 10, fontWeight: "800" },
  idText:     { flex: 1, fontSize: 12, color: "#e2e8f0", fontFamily: "monospace" },
  removeBtn:  { fontSize: 13, color: "#ef4444", paddingHorizontal: 4 },
  overlay:    { flex: 1, backgroundColor: "#00000088", justifyContent: "flex-end" },
  modal:      { backgroundColor: "#0F1F3D", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40, borderTopWidth: 1, borderColor: "#1e3a5f" },
  modalTitle: { fontSize: 16, fontWeight: "800", color: "#e2e8f0", marginBottom: 16 },
  modalLabel: { fontSize: 11, color: "#94a3b8", fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 8 },
  chainRow:   { flexDirection: "row", gap: 8, marginBottom: 16 },
  chainBtn:   { flex: 1, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: "#1e3a5f", alignItems: "center" },
  chainBtnText: { fontSize: 12, fontWeight: "800" },
  input:      { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 13, fontFamily: "monospace", marginBottom: 4 },
  hint:       { fontSize: 11, color: "#4a7fa5", fontStyle: "italic" },
  error:      { fontSize: 12, color: "#ef4444", marginTop: 6 },
});

function PhoneManager() {
  const [phone, setPhone] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(PHONE_STORE).then(v => { if (v) setPhone(v); });
  }, []);

  async function savePhone() {
    const clean = phone.trim().replace(/\s/g, "");
    if (!clean) return;
    await SecureStore.setItemAsync(PHONE_STORE, clean);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <View>
      <Text style={em.slotLabel}>Phone Number (E.164 format)</Text>
      <TextInput
        style={em.input}
        value={phone}
        onChangeText={setPhone}
        placeholder="+12125551234"
        placeholderTextColor="#334155"
        keyboardType="phone-pad"
        autoCorrect={false}
      />
      <Text style={[em.limitNote, { marginBottom: 6 }]}>Used for SIM swap monitoring. Must include country code.</Text>
      <TouchableOpacity style={em.saveBtn} onPress={savePhone}>
        <Text style={em.saveBtnText}>{saved ? "✓ Saved" : "Save Phone Number"}</Text>
      </TouchableOpacity>
    </View>
  );
}

interface PlanInfo { plan: string; intel_access: boolean; calls_this_month: number; }

const GAS_THRESHOLD_STORE   = "cs_gas_threshold";

export function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const { apiKey, saveApiKey } = useWallets();
  const [gasThreshold,    setGasThreshold]    = useState("20");
  const [saved,           setSaved]           = useState(false);
  const [savedGas,        setSavedGas]        = useState(false);
  const [pushAlerts,      setPushAlerts]      = useState(true);
  const [criticalOnly,    setCriticalOnly]    = useState(false);
  const [plan,            setPlan]            = useState<PlanInfo | null>(null);
  const [loadingPlan,     setLoadingPlan]     = useState(false);
  const { checkEnabled: updateCheckEnabled, setCheckEnabled: setUpdateCheckEnabled } = useUpdateCheck();

  useEffect(() => {
    if (apiKey) { fetchPlan(apiKey); }
  }, [apiKey]);

  async function fetchPlan(key: string) {
    setLoadingPlan(true);
    try {
      const info = await RS.getAccountInfo(key);
      setPlan({ plan: info.plan ?? "personal", intel_access: !!info.intel_access, calls_this_month: info.calls_this_month ?? 0 });
      await SecureStore.setItemAsync(PLAN_STORE, JSON.stringify(info));
    } catch { setPlan(null); }
    setLoadingPlan(false);
  }

  useEffect(() => {
    (async () => {
      const g = await SecureStore.getItemAsync(GAS_THRESHOLD_STORE);
      if (g) setGasThreshold(g);
    })();
  }, []);

  async function saveGasThreshold() {
    await SecureStore.setItemAsync(GAS_THRESHOLD_STORE, gasThreshold.trim());
    setSavedGas(true);
    setTimeout(() => setSavedGas(false), 2000);
  }

  const [linkEmail, setLinkEmail] = useState("");
  const [linking,   setLinking]   = useState(false);
  const [linkError, setLinkError] = useState("");
  const [openingPortal, setOpeningPortal] = useState(false);

  async function handleManageSubscription() {
    if (!apiKey) return;
    setOpeningPortal(true);
    try {
      const url = await RS.getCryptoShieldBillingPortalUrl({ apiKey });
      await Linking.openURL(url);
    } catch (err: any) {
      Alert.alert("Couldn't open billing", err?.message ?? "Try again in a moment.");
    }
    setOpeningPortal(false);
  }

  async function handleLinkSubscription() {
    const email = linkEmail.trim();
    if (!email || !email.includes("@")) { setLinkError("Enter a valid email address."); return; }
    setLinking(true);
    setLinkError("");
    try {
      const key = await RS.linkCryptoShieldSubscription(email);
      await saveApiKey(key);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      setLinkError(err?.message ?? "Could not find a subscription for that email.");
    }
    setLinking(false);
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Text style={styles.title}>Settings</Text>
      <ScrollView showsVerticalScrollIndicator={false} style={{ paddingHorizontal: 20 }}>

        <Text style={styles.groupHeader}>ACCOUNT</Text>

        {/* Link subscription — auto-linked on purchase; email is the manual fallback */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Subscription</Text>
          {apiKey ? (
            <>
              <Text style={{ fontSize: 12, color: "#22c55e", marginBottom: 10, fontWeight: "600" }}>
                ✓ Linked — live scans are unlocked
              </Text>
              <TouchableOpacity
                style={{ borderWidth: 1, borderColor: "#00B5A5", borderRadius: 10, paddingVertical: 11, alignItems: "center" }}
                onPress={handleManageSubscription}
                disabled={openingPortal}
              >
                {openingPortal
                  ? <ActivityIndicator color="#00B5A5" />
                  : <Text style={{ color: "#00B5A5", fontWeight: "700", fontSize: 13 }}>Manage Subscription</Text>}
              </TouchableOpacity>
              <Text style={{ fontSize: 11, color: "#475569", marginTop: 6 }}>
                Cancel, update your card, or view invoices — no need to email support.
              </Text>
            </>
          ) : (
            <>
              <Text style={styles.sectionDesc}>
                Already subscribed to Crypto Shield Pro? This usually links automatically right
                after checkout. If it didn't, enter the email you used at checkout below — live
                scans are already included in your subscription, no extra charge and no separate
                signup.
              </Text>
              <TextInput
                style={styles.input}
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
              <TouchableOpacity style={styles.saveBtn} onPress={handleLinkSubscription} disabled={linking}>
                <Text style={styles.saveBtnText}>{linking ? "Checking…" : "Unlock My Subscription"}</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        <Text style={styles.groupHeader}>MONITORING</Text>

        {/* Monitored Emails */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Monitored Emails</Text>
          <Text style={styles.sectionDesc}>
            Up to 3 email addresses monitored for breach exposure and infostealer activity. Alerts fire when credentials appear in criminal archives.
          </Text>
          <EmailManager />
        </View>

        {/* Phone Number */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Phone Number</Text>
          <Text style={styles.sectionDesc}>
            Used for SIM swap monitoring. Enter the phone number associated with your crypto exchange accounts.
          </Text>
          <PhoneManager />
        </View>

        {/* NFT Collection Monitoring */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>NFT Floor Monitoring</Text>
          <Text style={styles.sectionDesc}>
            Get push alerts when an NFT collection floor drops ≥15%. Supports Solana (Magic Eden slug), EVM (contract address), and TON collections. Up to 10 collections.
          </Text>
          <NFTCollectionManager />
        </View>

        <Text style={styles.groupHeader}>ALERTS</Text>

        {/* Gas Alert Threshold */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Gas Alert Threshold</Text>
          <Text style={styles.sectionDesc}>
            Get notified when ETH gas drops below this level — a good time to transact.
          </Text>
          <Text style={styles.fieldLabel}>Threshold (gwei)</Text>
          <TextInput style={styles.input} value={gasThreshold} onChangeText={setGasThreshold}
            placeholder="e.g. 20" placeholderTextColor="#334155" keyboardType="numeric" />
          <TouchableOpacity style={styles.saveBtn} onPress={saveGasThreshold}>
            <Text style={styles.saveBtnText}>{savedGas ? "✓ Saved" : "Save Threshold"}</Text>
          </TouchableOpacity>
        </View>

        {/* Notifications */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Push Notifications</Text>
          <ToggleRow
            label="Alert notifications"
            sub="Receive push alerts for new threat findings"
            value={pushAlerts}
            onChange={setPushAlerts}
          />
          <ToggleRow
            label="Critical only"
            sub="Only notify for CRITICAL severity — suppress HIGH/MEDIUM"
            value={criticalOnly}
            onChange={setCriticalOnly}
          />
        </View>

        {/* Updates */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Updates</Text>
          <ToggleRow
            label="Check for updates"
            sub="Show a banner when a newer version is available on the dApp Store"
            value={updateCheckEnabled}
            onChange={setUpdateCheckEnabled}
          />
        </View>

        {/* Scan schedule */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Monitoring</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Scan frequency</Text>
            <Text style={styles.infoValue}>Every 6 hours</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Signals checked</Text>
            <Text style={styles.infoValue}>6 dimensions</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Vendor sweep</Text>
            <Text style={styles.infoValue}>Weekly</Text>
          </View>
        </View>

        <Text style={styles.groupHeader}>SUBSCRIPTION</Text>

        {/* Account & Plan */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Account & Plan</Text>
          {loadingPlan ? (
            <Text style={[styles.sectionDesc, { color: "#00B5A5" }]}>Checking plan…</Text>
          ) : plan ? (
            <View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>Plan</Text>
                <Text style={styles.infoValue}>{plan.plan.toUpperCase()}</Text>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>TI Access</Text>
                <Text style={[styles.infoValue, { color: plan.intel_access ? "#22c55e" : "#64748b" }]}>
                  {plan.intel_access ? "✓ Active" : "Not included"}
                </Text>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>API calls this month</Text>
                <Text style={styles.infoValue}>{plan.calls_this_month.toLocaleString()}</Text>
              </View>
              {!plan.intel_access && (
                <TouchableOpacity
                  style={[styles.saveBtn, { marginTop: 12, backgroundColor: "#7c3aed" }]}
                  onPress={() => navigation.navigate("Paywall")}
                >
                  <Text style={styles.saveBtnText}>Upgrade to Pro →</Text>
                </TouchableOpacity>
              )}
            </View>
          ) : (
            <TouchableOpacity
              style={styles.saveBtn}
              onPress={() => navigation.navigate("Paywall")}
            >
              <Text style={styles.saveBtnText}>View Plans & Pricing →</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={[styles.linkRow, { marginTop: 8 }]} onPress={() => Alert.alert("Contact Support", "Email us at support@relayshield.net\n\nWe typically respond within 24 hours.", [{ text: "OK" }])}>
            <Text style={styles.linkText}>Contact support →</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.linkRow} onPress={() => navigation.navigate("Tour")}>
            <Text style={styles.linkText}>Replay app tour →</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.groupHeader}>ABOUT</Text>

        {/* Security & Trust */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Security & Trust</Text>
          {[
            "Read-only by design: Crypto Shield never requests seed phrases, private keys, or wallet permissions — only public addresses.",
            "Every wallet alert is signature-verified before delivery, so alerts can't be spoofed or faked.",
            "We only hold the email and phone number you provide for monitoring — billing details (including any address) are handled directly by Stripe, our payment processor, and never stored in our systems.",
            "Infrastructure protected by encrypted storage, automated backups, and a documented incident response plan.",
            "RelayShield carries active Tech E&O and Cyber insurance coverage.",
          ].map(point => (
            <View key={point} style={styles.trustRow}>
              <Text style={styles.trustCheck}>✓</Text>
              <Text style={styles.trustText}>{point}</Text>
            </View>
          ))}
        </View>

        {/* Resources */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Resources</Text>
          {[
            { label: "Website",       url: "https://relayshield.net",                        icon: "🌐" },
            { label: "API Docs",      url: "https://api.relayshield.net/developers",         icon: "📄" },
            { label: "System Status", url: "https://stats.uptimerobot.com/lsa89C5S8W",     icon: "📡" },
            { label: "Blog",          url: "https://blog.relayshield.net",                icon: "✍" },
            // Repointed 2026-08-10 from t.me/RelayShield, the broadcast channel,
            // which has 4 subscribers. The bot is the live product: it scans a
            // link or address for free, and can be added to a group chat.
            { label: "Telegram bot",  url: "https://t.me/relayshield_bot?start=src_csmobile", icon: "✈" },
          ].map(r => (
            <TouchableOpacity key={r.label} style={styles.resourceRow} onPress={() => Linking.openURL(r.url)}>
              <Text style={styles.resourceIcon}>{r.icon}</Text>
              <Text style={styles.resourceLabel}>{r.label}</Text>
              <Text style={styles.resourceArrow}>→</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Community & socials */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Community</Text>
          <Text style={styles.sectionDesc}>
            Follow us for threat briefings, product updates, and security research.
          </Text>
          <View style={styles.socialGrid}>
            {[
              // X removed 2026-08-10: @RelayShieldHQ has been suspended since
              // 2026-07-02 and the appeal was denied, so this button sent users
              // to a suspended-account page.
              { label: "LinkedIn",    url: "https://linkedin.com/company/relayshield",            icon: "in", color: "#0a66c2" },
              // Repointed from the 4-subscriber channel to the bot, same as above.
              { label: "Telegram",    url: "https://t.me/relayshield_bot?start=src_csmobile",     icon: "✈",  color: "#2AABEE" },
              { label: "Farcaster",   url: "https://warpcast.com/cryptonomicon",                  icon: "⬡",  color: "#8b5cf6" },
              { label: "Mastodon",    url: "https://infosec.exchange/@relayshieldadmin",          icon: "🐘", color: "#6364ff" },
            ].map(s => (
              <TouchableOpacity key={s.label} style={styles.socialBtn} onPress={() => Linking.openURL(s.url)}>
                <Text style={[styles.socialIcon, { color: s.color }]}>{s.icon}</Text>
                <Text style={styles.socialLabel}>{s.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <Text style={styles.footer}>Crypto Shield · RelayShield LLC · © 2026</Text>
        <Text style={styles.footerVersion}>
          v{Constants.expoConfig?.version ?? "?"}
          {Constants.expoConfig?.android?.versionCode ? ` (${Constants.expoConfig.android.versionCode})` : ""}
        </Text>
        <View style={styles.footerLinks}>
          <TouchableOpacity onPress={() => Linking.openURL("https://privacy.relayshield.net")}>
            <Text style={styles.footerLink}>Privacy Policy</Text>
          </TouchableOpacity>
          <Text style={styles.footerDot}>·</Text>
          <TouchableOpacity onPress={() => Linking.openURL("https://terms.relayshield.net")}>
            <Text style={styles.footerLink}>Terms of Service</Text>
          </TouchableOpacity>
        </View>
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

function ToggleRow({ label, sub, value, onChange }: {
  label: string; sub: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <View style={styles.toggleRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.toggleLabel}>{label}</Text>
        <Text style={styles.toggleSub}>{sub}</Text>
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: "#00B5A5", false: "#1e3a5f" }} thumbColor="#fff" />
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: "#0a1628" },
  title:        { fontSize: 20, fontWeight: "800", color: "#fff", padding: 20, paddingBottom: 10 },
  groupHeader:  { fontSize: 10, fontWeight: "800", color: "#334155", letterSpacing: 1.2, marginBottom: 8, marginTop: 4, paddingLeft: 4 },
  section:      { backgroundColor: "#0F1F3D", borderRadius: 12, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: "#e2e8f0", marginBottom: 4 },
  sectionDesc:  { fontSize: 12, color: "#64748b", lineHeight: 18, marginBottom: 12 },
  input:        { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 8, padding: 12, color: "#e2e8f0", fontSize: 13, fontFamily: "monospace", marginBottom: 10 },
  saveBtn:      { backgroundColor: "#00B5A5", borderRadius: 8, paddingVertical: 10, alignItems: "center" },
  saveBtnText:  { color: "#0a1628", fontWeight: "800", fontSize: 13 },
  toggleRow:    { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a", gap: 12 },
  toggleLabel:  { fontSize: 13, color: "#e2e8f0", fontWeight: "600" },
  toggleSub:    { fontSize: 11, color: "#64748b", marginTop: 2 },
  infoRow:      { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  infoLabel:    { fontSize: 13, color: "#94a3b8" },
  infoValue:    { fontSize: 13, color: "#00B5A5", fontWeight: "600" },
  linkRow:      { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  linkText:     { fontSize: 13, color: "#00B5A5", fontWeight: "600" },
  fieldLabel:   { fontSize: 11, color: "#e2e8f0", fontWeight: "700", letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 6, marginTop: 4 },
  resourceRow:  { flexDirection: "row", alignItems: "center", paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: "#1e3a5f1a" },
  resourceIcon: { fontSize: 15, width: 26 },
  resourceLabel:{ fontSize: 13, color: "#e2e8f0", flex: 1, fontWeight: "500" },
  resourceArrow:{ fontSize: 14, color: "#4a7fa5" },
  trustRow:     { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 10 },
  trustCheck:   { fontSize: 13, color: "#00B5A5", fontWeight: "800", marginTop: 1 },
  trustText:    { fontSize: 12, color: "#94a3b8", flex: 1, lineHeight: 17 },
  socialGrid:   { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  socialBtn:    { backgroundColor: "#060b18", borderWidth: 1, borderColor: "#1e3a5f", borderRadius: 10, paddingVertical: 10, paddingHorizontal: 12, alignItems: "center", minWidth: "28%" as any, flex: 1 },
  socialIcon:   { fontSize: 16, marginBottom: 4, fontWeight: "700" },
  socialLabel:  { fontSize: 9, color: "#64748b", fontWeight: "600", textAlign: "center" },
  footer:       { fontSize: 11, color: "#334155", textAlign: "center", marginTop: 10 },
  footerVersion:{ fontSize: 10, color: "#334155", textAlign: "center", marginTop: 2, fontFamily: "monospace" },
  footerLinks:  { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, marginTop: 6, marginBottom: 4 },
  footerLink:   { fontSize: 11, color: "#4a7fa5", textDecorationLine: "underline" },
  footerDot:    { fontSize: 11, color: "#334155" },
});
