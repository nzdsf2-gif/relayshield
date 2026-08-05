// Mobile Wallet Adapter — read-only "connect" only.
// Requests authorize() to learn the wallet's public address; never requests
// signing. Keeps Crypto Shield's "we never touch your keys" model intact —
// the wallet app (Phantom, Solflare, etc.) holds the keys throughout.
import { transact } from "@solana-mobile/mobile-wallet-adapter-protocol-web3js";
import { PublicKey } from "@solana/web3.js";

const APP_IDENTITY = {
  name: "Crypto Shield Mobile",
  uri: "https://cryptoshieldmobile.relayshield.net",
  icon: "favicon.ico",
};

export async function connectSolanaWallet(): Promise<string> {
  const result = await transact(async (wallet) => {
    return wallet.authorize({
      cluster: "mainnet-beta",
      identity: APP_IDENTITY,
    });
  });

  const account = result.accounts[0];
  if (!account) throw new Error("No account returned by wallet");

  return new PublicKey(Buffer.from(account.address, "base64")).toBase58();
}
