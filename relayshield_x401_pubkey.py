"""relayshield_x401_pubkey -- the PUBLIC half of the x401 verifier's request-signing key.

Served by relayshield-api as the did:web document at
https://api.relayshield.net/.well-known/did.json, which is how a wallet that has never
heard of us checks the signature on our OpenID4VP request (client_id
`decentralized_identifier:did:web:api.relayshield.net`).

THIS FILE HOLDS NO SECRET. It is the public JWK only. The private key lives in Secrets
Manager (relayshield/x401_verifier_key) and is written there by
tools/generate_x401_verifier_key.py, which also rewrites PUBLIC_JWK below.

It is named relayshield_* so the deployer's dependency walk packages it with relayshield-api.

While PUBLIC_JWK is None the did:web document answers 404 and signed requests cannot be
verified by any wallet: the verifier is "not configured", not "configured insecurely".
"""

PUBLIC_JWK = None
KID = "did:web:api.relayshield.net#x401-1"
