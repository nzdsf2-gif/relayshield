# Your wallet agent moves real money. Screen every payment before it moves.

Date: 2026-11-23

Your wallet agent moves real money. Every payment it sends is irreversible once the wallet signs it. One bad payTo address, one scam counterparty, one pinned payee that drifted, and the money is gone.

RelayShield now screens the payTo address before the payment moves. Before your Coinbase Wallet agent calls the payment tool, it calls counterparty-screen on the recipient: $0.10, live today, against 850K+ indicators from 144 monitored marketplaces. If you pinned the payee, pin-check confirms the address still matches, $0.02. A HIGH verdict or a pin mismatch stops the payment and tells the human why. A timeout or an unknown returns a note, not a block, because the human still approves every payment.

It works today. No Coinbase code change, no new endpoint. The screen runs in the agent's payment flow, the same pattern that already works with MetaMask. And when you want the screen enforced rather than advised, the MCP Proxy Firewall puts the same check at the gate, where the agent cannot skip it. $49 a month, 20,000 screened calls included.

Your wallet agent moves real money. Give it a screen before every payment, and a firewall behind it.
