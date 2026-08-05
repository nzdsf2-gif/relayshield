// Gamification state — streak, shield score, referral code
import { useState, useEffect, useCallback } from "react";
import * as SecureStore from "expo-secure-store";

const STREAK_KEY    = "cs_streak";
const SCORE_KEY     = "cs_shield_score";
const REFERRAL_KEY  = "cs_referral_code";
const LAST_SCAN_KEY = "cs_last_scan_date";

export interface GameState {
  streak: number;
  shieldScore: number;
  referralCode: string;
  lastScanDate: string | null;
}

export function useGamification() {
  const [state, setState] = useState<GameState>({
    streak: 0, shieldScore: 0, referralCode: "", lastScanDate: null,
  });

  useEffect(() => { load(); }, []);

  async function load() {
    const [streakRaw, scoreRaw, code, lastScan] = await Promise.all([
      SecureStore.getItemAsync(STREAK_KEY),
      SecureStore.getItemAsync(SCORE_KEY),
      SecureStore.getItemAsync(REFERRAL_KEY),
      SecureStore.getItemAsync(LAST_SCAN_KEY),
    ]);
    setState({
      streak:      parseInt(streakRaw || "0"),
      shieldScore: parseInt(scoreRaw  || "0"),
      referralCode: code || _generateCode(),
      lastScanDate: lastScan,
    });
  }

  // Call when user performs a security action (scan, sweep, approval revoke)
  const recordActivity = useCallback(async (points: number = 10) => {
    const today     = new Date().toDateString();
    const lastScan  = await SecureStore.getItemAsync(LAST_SCAN_KEY);
    const yesterday = new Date(Date.now() - 86400000).toDateString();

    let streak = parseInt((await SecureStore.getItemAsync(STREAK_KEY)) || "0");
    if (lastScan === yesterday) streak += 1;
    else if (lastScan !== today) streak = 1; // reset if gap

    const score = Math.min(1000, parseInt((await SecureStore.getItemAsync(SCORE_KEY)) || "0") + points);

    await Promise.all([
      SecureStore.setItemAsync(STREAK_KEY,    String(streak)),
      SecureStore.setItemAsync(SCORE_KEY,     String(score)),
      SecureStore.setItemAsync(LAST_SCAN_KEY, today),
    ]);

    setState(prev => ({ ...prev, streak, shieldScore: score, lastScanDate: today }));
    return { streak, score, isNewDay: lastScan !== today };
  }, []);

  // Call when user revokes an approval or rejects a poisoned signature
  const recordThreatIntercepted = useCallback(async () => {
    return recordActivity(25); // bonus points for active threat response
  }, [recordActivity]);

  return { ...state, recordActivity, recordThreatIntercepted };
}

function _generateCode(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let code = "RS-";
  for (let i = 0; i < 6; i++) code += chars[Math.floor(Math.random() * chars.length)];
  SecureStore.setItemAsync(REFERRAL_KEY, code);
  return code;
}

// Achievement definitions
export const ACHIEVEMENTS = [
  { id: "first_scan",      icon: "🔍", title: "First Scan",        desc: "Run your first threat intelligence check",   threshold: 1,   metric: "scans" },
  { id: "week_streak",     icon: "🔥", title: "Week Guardian",     desc: "7-day security check streak",                threshold: 7,   metric: "streak" },
  { id: "honeypot_hunter", icon: "🍯", title: "Honeypot Hunter",   desc: "Detected 5 risky or honeypot tokens",        threshold: 5,   metric: "risky_tokens" },
  { id: "approval_slayer", icon: "⚔️", title: "Approval Slayer",   desc: "Revoked 10 dangerous token approvals",       threshold: 10,  metric: "revoked_approvals" },
  { id: "clean_sweep",     icon: "✨", title: "Clean Sweep",       desc: "Zero open alerts for 7 consecutive days",    threshold: 7,   metric: "clean_days" },
  { id: "shield_100",      icon: "🛡", title: "Shield 100",        desc: "Reached Shield Score 100",                   threshold: 100, metric: "shield_score" },
  { id: "interceptor",     icon: "🚫", title: "Attack Intercepted",desc: "Rejected a signature poisoning attempt",     threshold: 1,   metric: "intercepted" },
  { id: "referrer",        icon: "🤝", title: "Guardian Network",  desc: "Referred your first protected friend",       threshold: 1,   metric: "referrals" },
];
