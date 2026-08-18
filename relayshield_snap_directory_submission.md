# MetaMask Snaps Directory submission, prepared answers

Form: https://go.metamask.io/snaps-directory-request

Do npm publish FIRST. The form asks for the npm package link and a version number
that matches `package.json`, and the review checks a published package.

## Prepared answers

| Field | Answer |
|---|---|
| Snap name | RelayShield Counterparty Screening |
| Version | 0.1.0 |
| npm package | https://www.npmjs.com/package/relayshield-snap |
| Snap ID | `npm:relayshield-snap` |
| GitHub | https://github.com/nzdsf2-gif/relayshield-snap |
| Website | https://api.relayshield.net/developers?source=metamask-snap |
| Builder | RelayShield LLC |
| Support contact | support@relayshield.net |
| Audit report | Not applicable, see below |

**Short description**

Screens the counterparty address of every transaction against RelayShield's criminal
intelligence corpus before you sign.

**Long description**

RelayShield checks the address you are about to send to against a corpus built from criminal
Telegram channels, breach dumps, infostealer logs and public threat feeds, and shows the result
inside the transaction confirmation window.

It is deliberately explicit about what it does not know. If the check cannot complete, for any
reason, the snap says the address was not screened rather than showing an empty result that reads
like a pass. An upstream outage should never look like a clean bill of health at the moment
somebody is about to move money.

You bring your own RelayShield API key, so screening is billed to you at five cents a check and we
bundle no allowance you have to think about. The snap sends the counterparty address and nothing
else. It never sees your keys, your seed, your balances or your transaction history.

## Why no audit report

The allowlist requires a third-party audit only for snaps using `snap_getBip32Entropy`,
`snap_getBip44Entropy`, `snap_getEntropy` or `snap_manageAccounts`. This snap uses none of them.
Its full permission set is:

```
endowment:transaction-insight   read the pending transaction
endowment:network-access        call api.relayshield.net
endowment:page-home             settings screen
snap_manageState                store the user's own API key
```

`allowTransactionOrigin` is deliberately NOT requested. The snap does not need to know which dapp
initiated the transaction. If a reviewer asks why the permission set is so small, that is the
answer: it was scoped this way on purpose.

## Eligibility checklist, verified 2026-08-09

- [x] Source publicly available: https://github.com/nzdsf2-gif/relayshield-snap, MIT
- [ ] Published to npm: **BLOCKED, needs founder to run `npm login`**
- [x] No console logs in source
- [x] No unused code or permissions. `snap_dialog` was declared and never called, and was removed
      before submission rather than left for a reviewer to find
- [x] `package.json` and `snap.manifest.json` versions match at 0.1.0
- [x] `repository.url` matches the real repo
- [x] `source.location.npm.packageName` matches the package name
- [x] `proposedName` contains neither "MetaMask" nor "Snap", per their naming rule
- [x] Icon is SVG, renders on light and dark

## Still needed from the founder

1. `npm login`, then `npm publish` from `relayshield-snap/`. I cannot authenticate to npm.
2. Promotional images, if the form requires them. Not yet produced.

## Note on npm publish

`npm unpublish` is heavily restricted after 72 hours, so treat 0.1.0 as permanent once it is up.
Everything above was verified against the built package before this file was written: 5 files,
9.2 kB, no secrets.
