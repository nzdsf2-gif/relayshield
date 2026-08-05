import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

interface State { hasError: boolean; error: string }
interface Props { children: React.ReactNode; screenName?: string }

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error: error.message ?? "Unknown error" };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[ErrorBoundary] ${this.props.screenName ?? "Screen"} crashed:`, error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <View style={s.container}>
        <Text style={s.icon}>🛡</Text>
        <Text style={s.title}>Something went wrong</Text>
        <Text style={s.detail}>{this.state.error}</Text>
        <TouchableOpacity style={s.btn} onPress={() => this.setState({ hasError: false, error: "" })}>
          <Text style={s.btnText}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  }
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a1628", alignItems: "center", justifyContent: "center", padding: 32 },
  icon:      { fontSize: 48, marginBottom: 16 },
  title:     { fontSize: 18, fontWeight: "800", color: "#f1f5f9", marginBottom: 8, textAlign: "center" },
  detail:    { fontSize: 12, color: "#64748b", marginBottom: 32, textAlign: "center", lineHeight: 18 },
  btn:       { backgroundColor: "#00B5A5", borderRadius: 10, paddingVertical: 12, paddingHorizontal: 32 },
  btnText:   { color: "#0a1628", fontWeight: "800", fontSize: 14 },
});
