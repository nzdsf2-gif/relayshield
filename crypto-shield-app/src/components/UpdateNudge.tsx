import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

const DAPP_STORE_URL = "solanadappstore://details?id=net.relayshield.cryptoshieldmobile";

interface Props {
  latestVersion: string;
  onDismiss: () => void;
}

export function UpdateNudge({ latestVersion, onDismiss }: Props) {
  const insets = useSafeAreaInsets();

  async function openStore() {
    const supported = await Linking.canOpenURL(DAPP_STORE_URL);
    if (supported) {
      Linking.openURL(DAPP_STORE_URL);
    }
  }

  return (
    <View style={[s.banner, { top: insets.top + 6 }]} pointerEvents="box-none">
      <View style={s.inner}>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>Update available — v{latestVersion}</Text>
          <Text style={s.sub}>Tap to open the dApp Store and update.</Text>
        </View>
        <TouchableOpacity style={s.updateBtn} onPress={openStore}>
          <Text style={s.updateBtnText}>Update</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.dismissBtn} onPress={onDismiss}>
          <Text style={s.dismissBtnText}>✕</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  banner: {
    position: "absolute",
    left: 0,
    right: 0,
    zIndex: 100,
    paddingHorizontal: 16,
  },
  inner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#0F1F3D",
    borderWidth: 1,
    borderColor: "#00B5A5",
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    gap: 10,
  },
  title: { fontSize: 12, fontWeight: "700", color: "#e2e8f0" },
  sub: { fontSize: 10, color: "#64748b", marginTop: 1 },
  updateBtn: { backgroundColor: "#00B5A5", borderRadius: 6, paddingVertical: 6, paddingHorizontal: 10 },
  updateBtnText: { fontSize: 11, fontWeight: "800", color: "#0a1628" },
  dismissBtn: { padding: 4 },
  dismissBtnText: { fontSize: 13, color: "#64748b" },
});
