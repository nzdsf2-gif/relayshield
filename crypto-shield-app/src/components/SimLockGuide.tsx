import React from "react";
import { Modal, View, Text, StyleSheet, TouchableOpacity, ScrollView, Linking } from "react-native";

interface Props {
  visible: boolean;
  onClose: () => void;
}

const CARRIERS = [
  {
    name: "T-Mobile",
    icon: "📱",
    steps: [
      'Call T-Mobile at 1-800-937-8997 or visit a store.',
      'Ask to enable "SIM Lock" or "Number Lock" on your account.',
      'Set a unique SIM PIN — different from your account PIN.',
      'Enable account takeover protection (ATOP): my.t-mobile.com → Profile → Privacy and notifications.',
    ],
    url: "https://www.t-mobile.com/support/account/sim-lock",
    urlLabel: "T-Mobile SIM Lock page →",
  },
  {
    name: "AT&T",
    icon: "🔷",
    steps: [
      'Log in to myAT&T or call 1-800-331-0500.',
      'Request "NumberSync" lock and "Extra Security" for your wireless account.',
      'Add a passcode to your account that must be given before any SIM changes.',
      'Enable wireless account PIN at att.com → Manage account → Security.',
    ],
    url: "https://www.att.com/support/article/wireless/KM1009325/",
    urlLabel: "AT&T account security page →",
  },
  {
    name: "Verizon",
    icon: "🔴",
    steps: [
      'Call *611 or visit My Verizon.',
      'Request a "Number Lock" — prevents SIM swaps without your account PIN.',
      'Set a unique 6-digit account PIN at My Verizon → Account → Manage security.',
      'Enable port freeze to prevent number porting without in-store verification.',
    ],
    url: "https://www.verizon.com/support/account-pin-faqs/",
    urlLabel: "Verizon account PIN setup →",
  },
  {
    name: "United Kingdom",
    icon: "🇬🇧",
    steps: [
      'UK carriers (EE, O2, Vodafone, Three, etc.) don\'t share one SIM-lock hotline — contact your own provider.',
      'Ask for a "port-out PIN" or "port freeze" — required under Ofcom General Condition C7 rules on switching and porting.',
      'A port freeze blocks your number from being ported to another network without extra verification.',
      'If your provider refuses or can\'t explain their process, you can escalate to Ofcom.',
    ],
    url: "https://www.ofcom.org.uk/phones-and-broadband/",
    urlLabel: "Ofcom phones & broadband →",
  },
  {
    name: "European Union",
    icon: "🇪🇺",
    steps: [
      'There\'s no single EU-wide SIM-lock process — protections are required under Article 40 of the EECC (European Electronic Communications Code), but implementation is per carrier and per country.',
      'Contact your carrier and ask for a port-out lock, SIM-swap PIN, or in-person ID verification requirement on your account.',
      'If your carrier can\'t offer this, your country\'s national telecom regulator (coordinated at EU level by BEREC) handles enforcement — file a complaint if you\'re refused reasonable protection.',
      'ENISA publishes EU-wide guidance on SIM-swap risk if you want to see what your carrier is required to support.',
    ],
    url: "https://www.enisa.europa.eu/sites/default/files/publications/ENISA_REPORT-Countering_SIM_Swapping.pdf",
    urlLabel: "ENISA SIM-swap guidance →",
  },
  {
    name: "Other carriers",
    icon: "🌐",
    steps: [
      'Contact your carrier directly and ask for a SIM lock or port freeze.',
      'Request that SIM changes require in-person ID verification.',
      'Set a unique account PIN not used anywhere else.',
      'Ask if they offer "enhanced security" or "account takeover protection."',
    ],
    url: null,
    urlLabel: null,
  },
];

const WHY = [
  { icon: "⚠️", text: "A SIM swap takes minutes. Attackers call your carrier, impersonate you, and move your number to a SIM they control." },
  { icon: "📲", text: "Once they have your number, they reset exchange passwords via SMS 2FA and drain accounts before you notice." },
  { icon: "🔐", text: "A SIM lock requires the attacker to also know your carrier PIN — adding a second barrier they can't bypass remotely." },
];

export function SimLockGuide({ visible, onClose }: Props) {
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={s.container}>
        <View style={s.header}>
          <Text style={s.title}>SIM Lock Guide</Text>
          <TouchableOpacity onPress={onClose} style={s.closeBtn}>
            <Text style={s.closeText}>✕</Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={s.scroll} showsVerticalScrollIndicator={false}>

          {/* Why it matters */}
          <View style={s.section}>
            <Text style={s.sectionTitle}>Why SIM locks matter</Text>
            {WHY.map((w, i) => (
              <View key={i} style={s.whyRow}>
                <Text style={s.whyIcon}>{w.icon}</Text>
                <Text style={s.whyText}>{w.text}</Text>
              </View>
            ))}
          </View>

          {/* Carrier steps */}
          <Text style={s.sectionTitle}>Steps by carrier</Text>
          {CARRIERS.map(c => (
            <View key={c.name} style={s.carrierCard}>
              <View style={s.carrierHeader}>
                <Text style={s.carrierIcon}>{c.icon}</Text>
                <Text style={s.carrierName}>{c.name}</Text>
              </View>
              {c.steps.map((step, i) => (
                <View key={i} style={s.stepRow}>
                  <Text style={s.stepNum}>{i + 1}</Text>
                  <Text style={s.stepText}>{step}</Text>
                </View>
              ))}
              {c.url && (
                <TouchableOpacity style={s.linkBtn} onPress={() => Linking.openURL(c.url!)}>
                  <Text style={s.linkText}>{c.urlLabel}</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}

          {/* After locking */}
          <View style={[s.section, s.tipsBox]}>
            <Text style={s.sectionTitle}>After locking your SIM</Text>
            {[
              "Move exchange 2FA from SMS to an authenticator app (Google Authenticator, Authy).",
              "Never store crypto wallet seed phrases in cloud notes, email drafts, or screenshots.",
              "Use a unique email address for crypto exchanges — not your primary email.",
            ].map((tip, i) => (
              <View key={i} style={s.stepRow}>
                <Text style={s.bullet}>•</Text>
                <Text style={s.stepText}>{tip}</Text>
              </View>
            ))}
          </View>

          <View style={{ height: 40 }} />
        </ScrollView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  container:     { flex: 1, backgroundColor: "#0a1628" },
  header:        { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20, borderBottomWidth: 1, borderBottomColor: "#1e3a5f" },
  title:         { fontSize: 18, fontWeight: "800", color: "#e2e8f0" },
  closeBtn:      { padding: 4 },
  closeText:     { fontSize: 18, color: "#64748b" },
  scroll:        { flex: 1, padding: 20 },
  section:       { marginBottom: 20 },
  sectionTitle:  { fontSize: 11, fontWeight: "800", color: "#4a7fa5", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 12 },
  whyRow:        { flexDirection: "row", gap: 10, marginBottom: 10, alignItems: "flex-start" },
  whyIcon:       { fontSize: 16, width: 22 },
  whyText:       { fontSize: 13, color: "#94a3b8", flex: 1, lineHeight: 19 },
  carrierCard:   { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: "#1e3a5f" },
  carrierHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 12 },
  carrierIcon:   { fontSize: 18 },
  carrierName:   { fontSize: 15, fontWeight: "800", color: "#e2e8f0" },
  stepRow:       { flexDirection: "row", gap: 10, marginBottom: 8, alignItems: "flex-start" },
  stepNum:       { fontSize: 11, fontWeight: "800", color: "#00B5A5", width: 16, marginTop: 2 },
  bullet:        { fontSize: 14, color: "#00B5A5", width: 16 },
  stepText:      { fontSize: 13, color: "#94a3b8", flex: 1, lineHeight: 18 },
  linkBtn:       { marginTop: 8, borderTopWidth: 1, borderTopColor: "#1e3a5f", paddingTop: 10 },
  linkText:      { fontSize: 12, color: "#00B5A5", fontWeight: "600" },
  tipsBox:       { backgroundColor: "#0F1F3D", borderRadius: 10, padding: 14, borderWidth: 1, borderColor: "#1e3a5f" },
});
