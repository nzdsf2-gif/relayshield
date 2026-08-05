import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Circle, G } from "react-native-svg";

interface Props {
  score: number;   // 0–100
  size?: number;
}

function riskColor(score: number) {
  if (score >= 70) return "#ef4444";
  if (score >= 45) return "#f97316";
  if (score >= 22) return "#facc15";
  return "#22c55e";
}

function riskLabel(score: number) {
  if (score >= 70) return "CRITICAL";
  if (score >= 45) return "HIGH";
  if (score >= 22) return "MEDIUM";
  return "LOW";
}

export function RiskGauge({ score, size = 120 }: Props) {
  const r = (size / 2) - 10;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const color = riskColor(score);

  return (
    <View style={styles.container}>
      <Svg width={size} height={size}>
        <G rotation="-90" origin={`${size / 2}, ${size / 2}`}>
          <Circle
            cx={size / 2} cy={size / 2} r={r}
            stroke="#1e3a5f" strokeWidth={10} fill="none"
          />
          <Circle
            cx={size / 2} cy={size / 2} r={r}
            stroke={color} strokeWidth={10} fill="none"
            strokeDasharray={`${filled} ${circ - filled}`}
            strokeLinecap="round"
          />
        </G>
      </Svg>
      <View style={[styles.center, { width: size, height: size }]}>
        <Text style={[styles.score, { color }]}>{score}</Text>
        <Text style={styles.outOf}>/100</Text>
        <Text style={[styles.label, { color }]}>{riskLabel(score)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { position: "relative", alignItems: "center" },
  center: {
    position: "absolute", top: 0, left: 0,
    justifyContent: "center", alignItems: "center",
  },
  score: { fontSize: 26, fontWeight: "800" },
  outOf: { fontSize: 11, color: "#64748b", marginTop: -2 },
  label: { fontSize: 10, fontWeight: "700", letterSpacing: 0.5, marginTop: 2 },
});
