# RelayShield plugin for Claude Code

Two components:

- **`relayshield-agent-bait` skill.** Screens a repository's agent-facing
  instructions before you connect an agent to it.
- **`relayshield` MCP server.** Breach, SIM-swap, domain lookalike, OAuth
  watchlist and infostealer checks as callable tools.

## Install

```
claude plugin marketplace add nzdsf2-gif/relayshield
claude plugin install relayshield@relayshield
```

`claude plugin marketplace add ~/dev/relayshield` also works from a local clone,
and needs no push. The `owner/repo` form clones the repository's DEFAULT BRANCH,
so it resolves only once `main` carries `.claude-plugin/marketplace.json`.

The MCP server is launched with `uvx`, so you need [uv](https://docs.astral.sh/uv/)
installed. Nothing else: uvx resolves and runs the package in its own
environment.

## Why the MCP server dependency carries a floor

`plugin.json` pins `relayshield-mcp>=0.2.10`, and that floor is load-bearing
rather than tidiness.

`relayshield-mcp` 0.2.9 and earlier declare their own dependency as
`mcp>=1.0.0` with **no upper bound**. A resolver takes the newest thing allowed,
so a fresh install of those versions pulls `mcp` 2.x, and the server dies at
import:

```
AttributeError: 'Server' object has no attribute 'list_tools'
```

The wheel is fine. The dependency range is not, and the failure needs no change
on our side at all: someone else published a major version and the published
package broke, silently, for new installs only.

The floor makes it impossible for this plugin to install a version that cannot
start. If 0.2.10 is not published yet, the install fails **loudly here**, which
is much better than the alternative: a server that installs, starts, dies, and
presents to the user as "disconnected" with the configuration looking perfectly
correct.

## Configuration

The MCP server reads these from the environment. None is required to try it:
without a key the API answers with its payment requirements, which is a usable
discovery mode rather than an error.

| Variable | Meaning |
|---|---|
| `RELAYSHIELD_API_KEY` | subscription key |
| `RELAYSHIELD_X_PAYMENT` | x402 payment proof, for pay-as-you-go on Base |
| `RELAYSHIELD_API_URL` | override the API base |

Keys, including a free tier:
<https://api.relayshield.net/developers?source=claude-skill>
