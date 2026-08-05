// Wallet management hook — stores watched addresses in SecureStore
import { useState, useEffect } from "react";
import * as SecureStore from "expo-secure-store";

export interface WatchedWallet {
  address: string;
  label: string;       // user-assigned name e.g. "Main Wallet"
  chain: "solana" | "evm" | "bitcoin" | "ton";
  addedAt: string;
  lastRiskScore?: number;
  lastRiskLevel?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  lastChecked?: string;
}

const WALLETS_KEY = "cs_wallets";
const APIKEY_KEY  = "cs_api_key";
const PHONE_KEY   = "cs_phone_number";
const EMAIL_KEY   = "cs_monitored_emails";

export function useWallets() {
  const [wallets, setWallets] = useState<WatchedWallet[]>([]);
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const raw = await SecureStore.getItemAsync(WALLETS_KEY);
      const key = await SecureStore.getItemAsync(APIKEY_KEY);
      if (raw) setWallets(JSON.parse(raw));
      if (key) setApiKeyState(key);
      setLoading(false);
    })();
  }, []);

  async function saveApiKey(key: string) {
    await SecureStore.setItemAsync(APIKEY_KEY, key);
    setApiKeyState(key);
  }

  async function addWallet(wallet: Omit<WatchedWallet, "addedAt">) {
    const newWallet: WatchedWallet = { ...wallet, addedAt: new Date().toISOString() };
    const updated = [...wallets, newWallet];
    await SecureStore.setItemAsync(WALLETS_KEY, JSON.stringify(updated));
    setWallets(updated);
  }

  async function removeWallet(address: string) {
    const updated = wallets.filter(w => w.address !== address);
    await SecureStore.setItemAsync(WALLETS_KEY, JSON.stringify(updated));
    setWallets(updated);
  }

  async function updateWalletRisk(address: string, score: number, level: WatchedWallet["lastRiskLevel"]) {
    // Read fresh from SecureStore — avoids stale closure when called immediately after addWallet
    const raw = await SecureStore.getItemAsync(WALLETS_KEY);
    const current: WatchedWallet[] = raw ? JSON.parse(raw) : wallets;
    const updated = current.map(w =>
      w.address === address
        ? { ...w, lastRiskScore: score, lastRiskLevel: level, lastChecked: new Date().toISOString() }
        : w
    );
    await SecureStore.setItemAsync(WALLETS_KEY, JSON.stringify(updated));
    setWallets(updated);
  }

  async function getPhone(): Promise<string | null> {
    return SecureStore.getItemAsync(PHONE_KEY);
  }
  async function savePhone(phone: string): Promise<void> {
    await SecureStore.setItemAsync(PHONE_KEY, phone);
  }
  async function getEmails(): Promise<string[]> {
    const raw = await SecureStore.getItemAsync(EMAIL_KEY);
    return raw ? JSON.parse(raw).filter(Boolean) : [];
  }

  return { wallets, apiKey, loading, addWallet, removeWallet, updateWalletRisk, saveApiKey, getPhone, savePhone, getEmails };
}
