import React, { useState } from "react";
import { Modal, View, Text, TouchableOpacity, TextInput, StyleSheet, Linking, Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import * as RS from "../api/relayshield";
import { PUSH_TOKEN_KEY } from "../hooks/usePushNotifications";

export const FEEDBACK_STATE_KEY = "cs_feedback_state";
const POSITIVE_MOMENT_KEY = "cs_feedback_positive_moments";
const MOMENTS_BEFORE_ASKING = 3;

// Solana dApp Store deep-link scheme — links to the listing page, not a
// dedicated review composer (no such deep link is documented as of 2026-07).
// Falls back silently if the dApp Store app isn't installed (e.g. Play Store
// installs, or during testing).
const DAPP_STORE_LISTING_URL = "solanadappstore://details?id=net.relayshield.cryptoshieldmobile";

interface FeedbackState {
  asked?: boolean;
  submittedAt?: string;
}

export async function notePositiveMoment(): Promise<boolean> {
  const state: FeedbackState = JSON.parse((await SecureStore.getItemAsync(FEEDBACK_STATE_KEY)) || "{}");
  if (state.asked) return false;

  const count = parseInt((await SecureStore.getItemAsync(POSITIVE_MOMENT_KEY)) || "0", 10) + 1;
  await SecureStore.setItemAsync(POSITIVE_MOMENT_KEY, String(count));
  return count >= MOMENTS_BEFORE_ASKING;
}

interface Props {
  visible: boolean;
  onDone: () => void;
}

export function FeedbackPrompt({ visible, onDone }: Props) {
  const [step, setStep] = useState<"ask" | "up-comment" | "comment" | "thanks">("ask");
  const [comment, setComment] = useState("");

  async function markAsked() {
    await SecureStore.setItemAsync(FEEDBACK_STATE_KEY, JSON.stringify({ asked: true, submittedAt: new Date().toISOString() }));
  }

  async function pushToken(): Promise<string> {
    return (await SecureStore.getItemAsync(PUSH_TOKEN_KEY)) || "";
  }

  async function openStoreListing() {
    try {
      const supported = await Linking.canOpenURL(DAPP_STORE_LISTING_URL);
      if (supported) await Linking.openURL(DAPP_STORE_LISTING_URL);
    } catch {}
  }

  async function handleUp() {
    // Submit "up" immediately so it's captured even if the optional
    // comment step below is abandoned — the rating matters more than the quote.
    const token = await pushToken();
    if (token) RS.submitFeedback(token, "up");
    await markAsked();
    setStep("up-comment");
  }

  async function finishUp() {
    const trimmed = comment.trim();
    if (trimmed) {
      const token = await pushToken();
      // Second submit overwrites the rating-only record with one that also
      // carries the quote — same device, same backend record.
      if (token) RS.submitFeedback(token, "up", trimmed);
    }
    await openStoreListing();
    setStep("thanks");
  }

  async function handleDown() {
    setStep("comment");
  }

  async function submitComment() {
    const token = await pushToken();
    if (token) RS.submitFeedback(token, "down", comment.trim());
    await markAsked();
    setStep("thanks");
  }

  function close() {
    setStep("ask");
    setComment("");
    onDone();
  }

  return (
    <Modal visible={visible} transparent animationType="fade" statusBarTranslucent>
      <View style={s.backdrop}>
        <View style={s.card}>
          {step === "ask" && (
            <>
              <Text style={s.icon}>🛡</Text>
              <Text style={s.title}>Enjoying Crypto Shield?</Text>
              <Text style={s.body}>Your feedback helps us improve — and takes 10 seconds.</Text>
              <View style={s.row}>
                <TouchableOpacity style={s.thumbBtn} onPress={handleDown}>
                  <Text style={s.thumbIcon}>👎</Text>
                  <Text style={s.thumbText}>Not really</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.thumbBtn, s.thumbBtnUp]} onPress={handleUp}>
                  <Text style={s.thumbIcon}>👍</Text>
                  <Text style={[s.thumbText, s.thumbTextUp]}>Yes!</Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity style={s.skipBtn} onPress={close}>
                <Text style={s.skipText}>Not now</Text>
              </TouchableOpacity>
            </>
          )}

          {step === "up-comment" && (
            <>
              <Text style={s.icon}>💬</Text>
              <Text style={s.title}>What do you like most?</Text>
              <Text style={s.body}>Optional — great quotes may be featured on relayshield.net.</Text>
              <TextInput
                style={s.input}
                value={comment}
                onChangeText={setComment}
                placeholder="Your feedback..."
                placeholderTextColor="#475569"
                multiline
                numberOfLines={4}
              />
              <TouchableOpacity style={s.submitBtn} onPress={finishUp}>
                <Text style={s.submitText}>Send feedback</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.skipBtn} onPress={finishUp}>
                <Text style={s.skipText}>Skip</Text>
              </TouchableOpacity>
            </>
          )}

          {step === "comment" && (
            <>
              <Text style={s.icon}>📝</Text>
              <Text style={s.title}>What could be better?</Text>
              <Text style={s.body}>Tell us what's not working — we read every response.</Text>
              <TextInput
                style={s.input}
                value={comment}
                onChangeText={setComment}
                placeholder="Your feedback..."
                placeholderTextColor="#475569"
                multiline
                numberOfLines={4}
              />
              <TouchableOpacity style={s.submitBtn} onPress={submitComment}>
                <Text style={s.submitText}>Send feedback</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.skipBtn} onPress={close}>
                <Text style={s.skipText}>Skip</Text>
              </TouchableOpacity>
            </>
          )}

          {step === "thanks" && (
            <>
              <Text style={s.icon}>✓</Text>
              <Text style={s.title}>Thanks for the feedback!</Text>
              <TouchableOpacity style={s.submitBtn} onPress={close}>
                <Text style={s.submitText}>Close</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(10,22,40,0.88)", alignItems: "center", justifyContent: "center", padding: 24 },
  card: { width: "100%", maxWidth: 340, backgroundColor: "#0F1F3D", borderRadius: 20, padding: 26, borderWidth: 1, borderColor: "#1e3a5f", alignItems: "center" },

  icon: { fontSize: 40, marginBottom: 10 },
  title: { fontSize: 18, fontWeight: "800", color: "#f1f5f9", marginBottom: 8, textAlign: "center" },
  body: { fontSize: 13, color: "#94a3b8", lineHeight: 19, textAlign: "center", marginBottom: 20 },

  row: { flexDirection: "row", gap: 12, width: "100%", marginBottom: 14 },
  thumbBtn: { flex: 1, alignItems: "center", paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: "#1e3a5f", backgroundColor: "#0a1628" },
  thumbBtnUp: { borderColor: "#00B5A5" },
  thumbIcon: { fontSize: 24, marginBottom: 4 },
  thumbText: { fontSize: 12, fontWeight: "700", color: "#94a3b8" },
  thumbTextUp: { color: "#00B5A5" },

  input: { width: "100%", backgroundColor: "#0a1628", borderRadius: 10, borderWidth: 1, borderColor: "#1e3a5f", color: "#e2e8f0", padding: 12, fontSize: 13, minHeight: 90, textAlignVertical: "top", marginBottom: 14 },
  submitBtn: { width: "100%", backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 13, alignItems: "center" },
  submitText: { fontSize: 14, fontWeight: "800", color: "#0a1628" },

  skipBtn: { marginTop: 12, paddingVertical: 6 },
  skipText: { fontSize: 13, color: "#334155" },
});
