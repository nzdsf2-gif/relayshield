# n8n Discord, Show-and-Tell post

Post from the new **RelayShieldAdmin** Discord account.

Use the `n8n.io/workflows/<id>` URLs only. `creators.n8n.io/workflows/<id>` returns 200 but renders a
login page to anyone not signed in, so it is not a shareable link.

---

## The post

First post here. I build RelayShield, a security API. Third template just got approved, so sharing
the set.

They ended up covering the employee identity lifecycle, which was not planned:

**Joiner** https://n8n.io/workflows/17255
New-hire webhook, breach and infostealer check on the personal email, then provisions Google
Workspace.

**Mover** https://n8n.io/workflows/17386
Vendor and AI-tool approval requests, risk checks including an MCP registry check, routes to Slack
and Notion.

**Leaver** https://n8n.io/workflows/16694
Offboarding webhook, breach, infostealer and OAuth exposure check, alerts the manager.

All three use Slack, Notion and Gmail for the human steps. Happy to answer anything on how they are
wired.

---

## Notes

- Skip the verified-creator badge. It reads as self-congratulation in a community channel, and the
  three links show it anyway.
- Free tier (20 calls, no card) only if someone asks. Leading with it turns this into an ad.
- Watch for anyone asking for a Jira, Okta or Entra variant. That is a real signal about which stack
  the next template should target.
- Detail held back on purpose: node counts are 18 / 17 / 10, and each description on n8n.io has the
  full step-by-step. Use those if someone asks a follow-up.
