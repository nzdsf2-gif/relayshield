# Claude Commerce Agents: is there a play for RelayShield?

*Asked 2026-09-05 from a social post. Answered by reading `anthropics/commerce-agents` itself, which
is public and reachable from the build container, rather than the post.*

**Short answer: yes, but not the one the post suggests, and NOT a pull request.** The play is
content plus two endpoints we already have (one built, one scoped), aimed at the moment a deployment
mounts an MCP server beside a merchant agent.

## What it actually is, from its own README

- A **reference implementation**: seven pip packages, two agents (shopping, merchant), four demo
  verticals, running on the Messages API, the Agent SDK, and Managed Agents.
- **It charges nothing and changes nothing.** "Nothing places an order, charges a card, or changes
  a live listing: `checkout` renders the cart for the host to complete, and every merchant write is
  staged until a person approves it." Every company in it is fictional.
- **"Business rules, authorization, and compliance are the deployment's."** Stated outright. That
  sentence is the entire commercial seam.
- Safety is a first-class concept and the vocabulary is close to ours: "Fencing, **provenance
  gates**, caps, memory validation, and the merchant approval gate run inside the tool call and hold
  on all three paths." There is a `docs/safety.md`.
- **"the examples have no authentication and the MCP servers bind to loopback."**

## Three things the post got wrong or left out, and each changes the answer

1. **"Carts up 35%, shoppers 60% more likely to check out."** Those are not in the repo, and the
   repo cannot produce them: it does not check anyone out. They are claims about deployments.
   **MEASUREMENT DOCTRINE applies — do not repeat them anywhere, in any form.** They are somebody
   else's numbers about somebody else's traffic.
2. **"This is a reference implementation; it is not maintained and does not accept contributions."**
   Last line of the README. **There is no PR play.** We have just spent 45 days learning that lesson
   on `crewAIInc/crewAI#6550`; here the door is not slow, it is closed and labelled. Anyone
   proposing a contribution to this repo has not read it.
3. **"MCP connectors: None ship."** Both agents reach systems through backend interfaces, and a
   platform's own MCP server "is called from a backend method server-side; on Managed Agents the
   manifest mounts it beside the role's server, and the provenance gates stay in front of every
   write."

Point 3 is the one worth building around.

## Where we actually fit

A deployment takes this blueprint and **mounts an MCP server beside an agent that can stage price
changes, inventory moves and campaigns.** Two questions arise at exactly that moment, and they are
the two questions our agentic endpoints already answer:

| Question at mount time | Our answer |
|---|---|
| Is this MCP server the one it claims to be? | `mcp-registry-risk` — typosquat distance, criminal IOC corpus, domain registration age. **Live today.** |
| Do its tool descriptions, or its repo's `AGENTS.md`, tell the agent to do something the merchant never asked for? | `agent-bait-scan` — scoped in `agent_baiting_scope.md`, not built |

**The merchant agent is the sharper half of the story, not the shopping agent.** A shopping agent
buying from its own store has no counterparty risk worth pricing. A merchant agent has write access
to pricing, inventory and campaigns, gated by human approval — and **a staged change that a human
rubber-stamps is still a change.** A tool description is instructions the model reads with the same
weight as a user's message, which is the whole premise of `agent-bait-scan`.

## What NOT to do

- **No PR.** See above; the repo says so.
- **No checkout-fraud product.** `RelayShield_Strategy.md` already ranked that last, on crowded
  incumbents holding 52% share, and this repo does not process payments anyway. Nothing here changes
  that ranking.
- **No new product line.** Everything above is our existing catalogue pointed at a named audience.
  If this needs a new endpoint to be interesting, it is not interesting.

## The actual move, in cost order

1. **A blog post**, and it is unusually well-founded for one: it rests on a primary source we can
   link, published by Anthropic, that says in its own words that authorization is the deployment's
   problem. Angle: *the reference implementation leaves authorization to you, and here is the check
   to run before you mount an MCP server beside an agent that can change your prices.* Canonical on
   `blog.relayshield.net`, then the usual channel order. Link the repo in the first paragraph, per
   house convention, and quote its own sentence rather than paraphrasing it.
2. **A `?source=commerce-agents` attribution key**, registered in `_SOURCE_BANNERS` BEFORE the post
   ships. FD-8 is what happens when that is skipped.
3. **`agent-bait-scan`**, which was already the recommendation and now has a second audience with a
   concrete deployment moment attached.

A Claude Code plugin of our own is the speculative fourth item. They ship a plugin marketplace in
that repo and a `/review-commerce-agent` command, so the shape exists — but building a plugin
against a repo that is explicitly unmaintained is spending a week on a moving target. Revisit only
if the blog post finds real readers.
