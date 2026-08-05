import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Path, Circle, Line, Defs, LinearGradient, Stop, G, Text as SvgText } from "react-native-svg";

interface Props {
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  size?: number;
}

const LEVEL_CONFIG = {
  LOW:      { angle: -130, label: "LOW RISK",      color: "#22c55e", pct: 0.08 },
  MEDIUM:   { angle:  -60, label: "MEDIUM RISK",   color: "#facc15", pct: 0.40 },
  HIGH:     { angle:   20, label: "HIGH RISK",      color: "#f97316", pct: 0.72 },
  CRITICAL: { angle:   90, label: "CRITICAL RISK",  color: "#ef4444", pct: 0.95 },
};

function polarToXY(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const s = polarToXY(cx, cy, r, startDeg);
  const e = polarToXY(cx, cy, r, endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
}

export function Speedometer({ riskLevel = "LOW", size = 200 }: Props) {
  const cx    = size / 2;
  const cy    = size / 2 + 10;
  const r     = size * 0.38;
  const track = size * 0.12;
  const cfg   = LEVEL_CONFIG[riskLevel] || LEVEL_CONFIG.LOW;

  // Needle
  const needle = polarToXY(cx, cy, r * 0.72, cfg.angle);

  return (
    <View style={styles.wrap}>
      <Svg width={size} height={size * 0.72}>
        <Defs>
          <LinearGradient id="arcGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <Stop offset="0%"   stopColor="#22c55e" stopOpacity="1" />
            <Stop offset="40%"  stopColor="#facc15" stopOpacity="1" />
            <Stop offset="75%"  stopColor="#f97316" stopOpacity="1" />
            <Stop offset="100%" stopColor="#ef4444" stopOpacity="1" />
          </LinearGradient>
        </Defs>

        {/* Background track */}
        <Path
          d={arcPath(cx, cy, r, -140, 140)}
          stroke="#1e3a5f"
          strokeWidth={track}
          fill="none"
          strokeLinecap="round"
        />

        {/* Colored arc up to risk level */}
        <Path
          d={arcPath(cx, cy, r, -140, cfg.angle)}
          stroke={cfg.color}
          strokeWidth={track}
          fill="none"
          strokeLinecap="round"
          opacity={0.9}
        />

        {/* Zone labels */}
        {[
          { label: "LOW",  angle: -115, color: "#22c55e" },
          { label: "MED",  angle:  -35, color: "#facc15" },
          { label: "HIGH", angle:   45, color: "#f97316" },
          { label: "CRIT", angle:  115, color: "#ef4444" },
        ].map(z => {
          const pos = polarToXY(cx, cy, r + track * 0.9, z.angle);
          return (
            <SvgText
              key={z.label}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              fontSize={size * 0.058}
              fill={z.color}
              fontWeight="700"
            >{z.label}</SvgText>
          );
        })}

        {/* Needle */}
        <Line
          x1={cx}
          y1={cy}
          x2={needle.x}
          y2={needle.y}
          stroke={cfg.color}
          strokeWidth={3}
          strokeLinecap="round"
        />

        {/* Center hub */}
        <Circle cx={cx} cy={cy} r={size * 0.055} fill={cfg.color} />
        <Circle cx={cx} cy={cy} r={size * 0.03}  fill="#0a1628" />
      </Svg>

      {/* Label below dial */}
      <Text style={[styles.level, { color: cfg.color }]}>{cfg.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap:  { alignItems: "center" },
  level: { fontSize: 15, fontWeight: "800", letterSpacing: 1, marginTop: -8 },
});
