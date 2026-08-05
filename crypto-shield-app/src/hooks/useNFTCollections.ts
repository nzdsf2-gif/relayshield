import { useEffect, useState } from "react";
import * as SecureStore from "expo-secure-store";

export const NFT_COLLECTIONS_KEY = "cs_nft_collections";

export type NFTChain = "solana" | "eth" | "base" | "ton";
export const NFT_CHAINS: NFTChain[] = ["solana", "eth", "base", "ton"];

export interface NFTCollection {
  chain: NFTChain;
  id: string;         // contract address, mint, or marketplace slug
  name?: string;       // optional display name
  addedAt?: string;    // optional timestamp
}

const CHAIN_SET = new Set(NFT_CHAINS);

// Single source of truth for cs_nft_collections. WalletsScreen.tsx and
// SettingsScreen.tsx previously each had their own independent reader/writer
// for this key with incompatible shapes ({contract, name, chain: "evm"} vs
// {chain, id}) — that mismatch caused a real crash when SettingsScreen hit an
// "evm" chain value it didn't recognize. This hook normalizes every legacy
// shape once, on read, and both screens now go through it instead of their
// own parsing.
function normalizeEntry(entry: any): NFTCollection | null {
  if (typeof entry === "string") {
    return { chain: "solana", id: entry }; // legacy string[] format
  }
  if (entry && entry.contract !== undefined) {
    // legacy WalletsScreen format — "evm" isn't a canonical chain value
    const chain = entry.chain === "evm" ? "eth" : entry.chain;
    return { chain, id: entry.contract || entry.name || "", name: entry.name, addedAt: entry.addedAt };
  }
  if (entry && entry.chain !== undefined && entry.id !== undefined) {
    return entry;
  }
  return null;
}

export function useNFTCollections() {
  const [collections, setCollections] = useState<NFTCollection[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(NFT_COLLECTIONS_KEY).then(v => {
      if (v) {
        const parsed = JSON.parse(v);
        const normalized = parsed
          .map(normalizeEntry)
          .filter((c: NFTCollection | null): c is NFTCollection => !!c && CHAIN_SET.has(c.chain) && !!c.id);
        setCollections(normalized);
        // Rewrite in canonical shape once, so future reads never need renormalizing
        if (JSON.stringify(normalized) !== JSON.stringify(parsed)) {
          SecureStore.setItemAsync(NFT_COLLECTIONS_KEY, JSON.stringify(normalized)).catch(() => {});
        }
      }
      setLoaded(true);
    });
  }, []);

  async function persist(updated: NFTCollection[]) {
    await SecureStore.setItemAsync(NFT_COLLECTIONS_KEY, JSON.stringify(updated));
    setCollections(updated);
  }

  async function addCollection(chain: NFTChain, id: string, name?: string): Promise<{ ok: boolean; error?: string }> {
    const trimmedId = id.trim();
    if (!trimmedId) return { ok: false, error: "Enter a collection ID." };
    if (collections.some(c => c.chain === chain && c.id.toLowerCase() === trimmedId.toLowerCase())) {
      return { ok: false, error: "Already in your watchlist." };
    }
    await persist([...collections, { chain, id: trimmedId, name, addedAt: new Date().toISOString() }]);
    return { ok: true };
  }

  async function removeCollection(chain: NFTChain, id: string) {
    await persist(collections.filter(c => !(c.chain === chain && c.id === id)));
  }

  return { collections, loaded, addCollection, removeCollection };
}
