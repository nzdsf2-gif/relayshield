// Full-screen "Attack Intercepted" animation — shown when user rejects
// a poisoned signature or acknowledges a CRITICAL threat
import React, { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated, Modal, TouchableOpacity } from "react-native";

interface Props {
  visible: boolean;
  type?: "signature_poisoning" | "honeypot" | "critical_alert" | "approval";
  onDismiss: () => void;
}

const TYPE_CONFIG = {
  signature_poisoning: { icon: "🚫", title: "Attack Blocked", sub: "Signature poisoning attempt rejected", color: "#ef4444" },
  honeypot:            { icon: "🍯", title: "Honeypot Detected", sub: "Token flagged before you could lose funds", color: "#f97316" },
  critical_alert:      { icon: "🛡", title: "Threat Acknowledged", sub: "You're responding faster than 99% of users", color: "#00B5A5" },
  approval:            { icon: "⚔️", title: "Approval Revoked", sub: "Dangerous spend access removed", color: "#22c55e" },
};

export function ThreatInterceptedAnimation({ visible, type = "critical_alert", onDismiss }: Props) {
  const scale   = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(0)).current;
  const ring1   = useRef(new Animated.Value(1)).current;
  const ring2   = useRef(new Animated.Value(1)).current;
  const cfg = TYPE_CONFIG[type];

  useEffect(() => {
    if (visible) {
      // Reset
      scale.setValue(0);
      opacity.setValue(0);
      ring1.setValue(1);
      ring2.setValue(1);

      Animated.parallel([
        Animated.spring(scale,   { toValue: 1, tension: 50, friction: 6, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
        Animated.loop(Animated.sequence([
          Animated.timing(ring1, { toValue: 1.8, duration: 800, useNativeDriver: true }),
          Animated.timing(ring1, { toValue: 1,   duration: 0,   useNativeDriver: true }),
        ]), { iterations: 3 }),
        Animated.loop(Animated.sequence([
          Animated.delay(300),
          Animated.timing(ring2, { toValue: 2.0, duration: 800, useNativeDriver: true }),
          Animated.timing(ring2, { toValue: 1,   duration: 0,   useNativeDriver: true }),
        ]), { iterations: 3 }),
      ]).start();

      // Auto-dismiss after 3s
      const t = setTimeout(onDismiss, 3000);
      return () => clearTimeout(t);
    }
  }, [visible]);

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onDismiss}>
      <Animated.View style={[styles.overlay, { opacity }]}>
        <Animated.View style={[styles.card, { transform: [{ scale }] }]}>

          {/* Pulsing rings */}
          <View style={styles.ringContainer}>
            <Animated.View style={[styles.ring, styles.ring1, {
              borderColor: cfg.color,
              transform: [{ scale: ring1 }],
              opacity: ring1.interpolate({ inputRange: [1, 1.8], outputRange: [0.6, 0] }),
            }]} />
            <Animated.View style={[styles.ring, styles.ring2, {
              borderColor: cfg.color,
              transform: [{ scale: ring2 }],
              opacity: ring2.interpolate({ inputRange: [1, 2], outputRange: [0.4, 0] }),
            }]} />

            {/* Icon circle */}
            <View style={[styles.iconCircle, { borderColor: cfg.color, shadowColor: cfg.color }]}>
              <Text style={styles.icon}>{cfg.icon}</Text>
            </View>
          </View>

          <Text style={[styles.title, { color: cfg.color }]}>{cfg.title}</Text>
          <Text style={styles.sub}>{cfg.sub}</Text>

          <View style={styles.scoreChip}>
            <Text style={styles.scoreText}>+25 Shield Score</Text>
          </View>

          <TouchableOpacity style={styles.dismissBtn} onPress={onDismiss}>
            <Text style={styles.dismissText}>Continue</Text>
          </TouchableOpacity>
        </Animated.View>
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay:     { flex: 1, backgroundColor: "#000000cc", justifyContent: "center", alignItems: "center" },
  card:        { backgroundColor: "#0F1F3D", borderRadius: 20, padding: 32, alignItems: "center", width: "80%", borderWidth: 1, borderColor: "#1e3a5f" },
  ringContainer:{ width: 120, height: 120, justifyContent: "center", alignItems: "center", marginBottom: 20 },
  ring:        { position: "absolute", width: 100, height: 100, borderRadius: 50, borderWidth: 2 },
  ring1:       {},
  ring2:       {},
  iconCircle:  { width: 80, height: 80, borderRadius: 40, borderWidth: 2, backgroundColor: "#060b18", justifyContent: "center", alignItems: "center", shadowOpacity: 0.6, shadowRadius: 12, shadowOffset: { width: 0, height: 0 }, elevation: 8 },
  icon:        { fontSize: 36 },
  title:       { fontSize: 22, fontWeight: "800", marginBottom: 8, textAlign: "center" },
  sub:         { fontSize: 13, color: "#94a3b8", textAlign: "center", lineHeight: 20, marginBottom: 16 },
  scoreChip:   { backgroundColor: "#00B5A520", borderRadius: 16, paddingHorizontal: 16, paddingVertical: 6, borderWidth: 1, borderColor: "#00B5A540", marginBottom: 20 },
  scoreText:   { fontSize: 13, color: "#00B5A5", fontWeight: "700" },
  dismissBtn:  { backgroundColor: "#1e3a5f", borderRadius: 10, paddingVertical: 10, paddingHorizontal: 24 },
  dismissText: { color: "#94a3b8", fontWeight: "600", fontSize: 13 },
});
