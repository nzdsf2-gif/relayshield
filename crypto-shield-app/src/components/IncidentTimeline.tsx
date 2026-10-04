import React from "react";
import { View, Text, StyleSheet } from "react-native";

// Result of POST /v1/metered/incident-timeline: one identity's breach, SIM swap
// and lookalike-domain signals, correlated into a named attack chain by the same
// ATTACK_CHAINS table the WhatsApp monitor uses.
//
// THREE STATES THAT MUST NEVER COLLAPSE INTO TWO. A check that came back clean,
// a check that could not be completed, and a check we never ran (no phone or
// domain was supplied) all produce "not flagged", and rendering any of them as
// "clear" is how a security product tells somebody they are safe on no
// evidence. `checked: false` is "could not check", never "clear", and a skipped
// check says what to add rather than saying nothing.

interface Check { checked?: boolean; flagged?: boolean; breach_count?: number | null; lookalikes_found?: number | null; highest_severity?: string | null; }

interface Props {
  data: {
    identity?: { email?: string; phone_checked?: boolean; domain_checked?: boolean };
    signals_detected?: string[];
    chain_matched?: { chain: string; severity: string; label: string; what: string } | null;
    checks?: { breach?: Check; session_risk?: Check; sim_swap?: Check; domain?: Check };
    checks_skipped?: string[];
  };
}

type NodeState = "flagged" | "clear" | "unknown" | "skipped";

const COLORS: Record<NodeState, string> = {
  flagged: "#ef4444",
  clear:   "#22c55e",
  unknown: "#facc15",
  skipped: "#334155",
};

function stateOf(check: Check | undefined): NodeState {
  if (!check) return "skipped";
  if (check.checked === false) return "unknown";
  return check.flagged ? "flagged" : "clear";
}

function severityColor(sev: string): string {
  const s = (sev ?? "").toUpperCase();
  if (s === "CRITICAL") return "#ef4444";
  if (s === "HIGH")     return "#f97316";
  return "#facc15";
}

export function IncidentTimeline({ data }: Props) {
  const checks = data.checks ?? {};
  const chain = data.chain_matched ?? null;

  const nodes: { key: string; icon: string; label: string; state: NodeState; detail: string }[] = [
    {
      key: "breach", icon: "💾", label: "Credential\nbreach", state: stateOf(checks.breach),
      detail: checks.breach?.flagged
        ? `${checks.breach.breach_count ?? "Some"} breach${checks.breach.breach_count === 1 ? "" : "es"} found`
        : "None found",
    },
    {
      key: "sim", icon: "📱", label: "SIM\nswap", state: stateOf(checks.sim_swap),
      detail: !checks.sim_swap ? "Add your phone number to check" : checks.sim_swap.flagged ? "Recent SIM change" : "None reported",
    },
    {
      key: "domain", icon: "🌐", label: "Lookalike\ndomain", state: stateOf(checks.domain),
      detail: !checks.domain ? "Add a domain to check"
        : checks.domain.flagged ? `${checks.domain.lookalikes_found ?? "Some"} found` : "None found",
    },
  ];
  // The two chains this endpoint can fire are breach + SIM swap and lookalike
  // domain + breach; a node that is part of the matched chain is the one to
  // draw the eye to.
  const inChain = (k: string) =>
    !!chain && ((k === "breach") || (k === "sim" && chain.chain === "breach_sim_swap")
      || (k === "domain" && chain.chain === "domain_phishing_breach"));

  const anyFlagged = nodes.some(n => n.state === "flagged");
  const anyUnknown = nodes.some(n => n.state === "unknown");

  const banner = chain
    ? { color: severityColor(chain.severity), title: `${chain.severity}: ${chain.label}`, body: chain.what }
    : anyFlagged
      ? { color: "#facc15", title: "Signals found, no attack chain",
          body: "At least one signal was found, but not the combination that marks a multi-stage attack. Treat it as an early warning and act on the individual finding." }
      : anyUnknown
        ? { color: "#facc15", title: "Could not complete every check",
            body: "One or more checks did not return, so this is not a clean result. Try again in a moment." }
        : { color: "#22c55e", title: "No attack chain found",
            body: "Nothing known against this identity in the signals checked." };

  const session = checks.session_risk;
  const sessionLine = !session ? null
    : session.checked === false ? "Session exposure: could not check"
    : session.flagged ? `Session exposure: found in criminal archives${session.highest_severity ? ` (${session.highest_severity})` : ""}`
    : "Session exposure: none found";

  return (
    <View style={styles.card}>
      <Text style={styles.title}>ATTACK SEQUENCE</Text>
      <Text style={styles.subtitle}>
        {data.identity?.email ? `For ${data.identity.email}` : "How the signals on this identity line up"}
      </Text>

      <View style={styles.track}>
        {nodes.map((n, i) => (
          <View key={n.key} style={styles.stageWrap}>
            {i > 0 && (
              <View style={[styles.connector, {
                backgroundColor: nodes[i - 1].state === "flagged" && n.state === "flagged" ? "#ef4444" : "#1e3a5f",
              }]} />
            )}
            <View style={styles.stageCol}>
              <View style={[styles.dot, { borderColor: COLORS[n.state] }, inChain(n.key) && chain ? styles.dotInChain : null]}>
                <Text style={[styles.dotIcon, { opacity: n.state === "skipped" ? 0.3 : 1 }]}>
                  {n.state === "flagged" ? n.icon : n.state === "unknown" ? "?" : n.state === "clear" ? "✓" : "·"}
                </Text>
              </View>
              <Text style={[styles.stageLabel, { color: n.state === "skipped" ? "#334155" : "#e2e8f0" }]}>{n.label}</Text>
              <Text style={[styles.detail, { color: n.state === "skipped" ? "#334155" : COLORS[n.state] }]}>{n.detail}</Text>
            </View>
          </View>
        ))}
      </View>

      <View style={[styles.banner, { borderColor: banner.color }]}>
        <Text style={[styles.bannerTitle, { color: banner.color }]}>{banner.title}</Text>
        <Text style={styles.bannerBody}>{banner.body}</Text>
      </View>

      {sessionLine ? <Text style={styles.session}>{sessionLine}</Text> : null}
      <Text style={styles.note}>
        Checks breach, SIM swap and lookalike-domain signals only. A result here is not proof an account is safe.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card:        { backgroundColor: "#060b18", borderRadius: 10, padding: 14, marginTop: 14, borderWidth: 1, borderColor: "#1e3a5f" },
  title:       { fontSize: 10, fontWeight: "700", color: "#4a7fa5", letterSpacing: 0.8, marginBottom: 2 },
  subtitle:    { fontSize: 11, color: "#64748b", marginBottom: 16 },
  track:       { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 },
  stageWrap:   { flex: 1, alignItems: "center", flexDirection: "row" },
  connector:   { flex: 1, height: 2, marginTop: -34, marginHorizontal: -2 },
  stageCol:    { alignItems: "center", flex: 1 },
  dot:         { width: 34, height: 34, borderRadius: 17, borderWidth: 2, backgroundColor: "#060b18", alignItems: "center", justifyContent: "center" },
  dotInChain:  { shadowColor: "#ef4444", shadowOpacity: 0.6, shadowRadius: 8, shadowOffset: { width: 0, height: 0 }, elevation: 6 },
  dotIcon:     { fontSize: 15, color: "#e2e8f0" },
  stageLabel:  { fontSize: 10, textAlign: "center", marginTop: 6, lineHeight: 13 },
  detail:      { fontSize: 9, textAlign: "center", marginTop: 3, lineHeight: 12, paddingHorizontal: 2 },
  banner:      { borderWidth: 1, borderRadius: 8, padding: 10 },
  bannerTitle: { fontSize: 13, fontWeight: "700", marginBottom: 4 },
  bannerBody:  { fontSize: 12, lineHeight: 18, color: "#cbd5e1" },
  session:     { fontSize: 11, color: "#94a3b8", marginTop: 10 },
  note:        { fontSize: 10, color: "#475569", marginTop: 8, lineHeight: 14 },
});
