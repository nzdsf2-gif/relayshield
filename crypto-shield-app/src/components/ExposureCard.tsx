import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import type { FreeExposureResult } from "../api/relayshield";
import { exposureView } from "../utils/exposureCopy";

interface Props {
  result: FreeExposureResult;
  onUpgrade: () => void;
  onRetry?: () => void;
}

const TONE: Record<string, { color: string; icon: string }> = {
  found:      { color: "#ef4444", icon: "🚨" },
  nothing:    { color: "#38bdf8", icon: "🔎" },   // deliberately not a green check: see exposureCopy.ts rule 1
  incomplete: { color: "#facc15", icon: "⚠️" },
  used:       { color: "#00B5A5", icon: "🔒" },
};

// Renders the words from utils/exposureCopy.ts and nothing else. Every sentence
// in here comes from that pure module so the "never says safe" and "never reads
// an unfinished check as clean" rules are tested by executing it.
export function ExposureCard({ result, onUpgrade, onRetry }: Props) {
  const v = exposureView(result);
  const t = TONE[v.tone];
  return (
    <View style={[s.card, { borderColor: t.color }]}>
      <View style={s.head}>
        <Text style={s.icon}>{t.icon}</Text>
        <Text style={[s.title, { color: t.color }]}>{v.title}</Text>
      </View>

      {v.lines.map((line, i) => (
        <Text key={i} style={s.line}>{line}</Text>
      ))}

      {v.actions.length > 0 && (
        <View style={s.actions}>
          <Text style={s.actionsHead}>What to do now</Text>
          {v.actions.map((a, i) => (
            <Text key={i} style={s.action}>• {a}</Text>
          ))}
        </View>
      )}

      {v.canRetry && onRetry && (
        <TouchableOpacity style={s.retry} onPress={onRetry}>
          <Text style={s.retryText}>Try again</Text>
        </TouchableOpacity>
      )}

      {v.cta && (
        <TouchableOpacity style={s.cta} onPress={onUpgrade} activeOpacity={0.85}>
          <Text style={s.ctaText}>{v.cta} →</Text>
        </TouchableOpacity>
      )}

      {!!v.note && <Text style={s.note}>{v.note}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card:        { backgroundColor: "#0F1F3D", borderWidth: 1, borderRadius: 14, padding: 16, marginTop: 14 },
  head:        { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  icon:        { fontSize: 24, marginRight: 10 },
  title:       { fontSize: 17, fontWeight: "800", flex: 1 },
  line:        { fontSize: 13, color: "#cbd5e1", lineHeight: 19, marginBottom: 6 },
  actions:     { backgroundColor: "#060b18", borderRadius: 10, padding: 12, marginTop: 8 },
  actionsHead: { fontSize: 12, fontWeight: "800", color: "#94a3b8", marginBottom: 6, letterSpacing: 0.4 },
  action:      { fontSize: 12.5, color: "#94a3b8", lineHeight: 18, marginBottom: 4 },
  retry:       { alignSelf: "flex-start", marginTop: 10, paddingVertical: 8, paddingHorizontal: 14,
                 borderRadius: 10, borderWidth: 1, borderColor: "#facc15" },
  retryText:   { color: "#facc15", fontWeight: "700", fontSize: 13 },
  cta:         { backgroundColor: "#00B5A5", borderRadius: 12, paddingVertical: 13, alignItems: "center", marginTop: 14 },
  ctaText:     { color: "#0a1628", fontWeight: "800", fontSize: 14 },
  note:        { fontSize: 10.5, color: "#475569", marginTop: 10, lineHeight: 15 },
});
