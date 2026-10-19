# Exposed MCP Server Scanner Check - Spec

## Concept
Free scanner check: "Is this MCP server exposed to the public internet?" Inspired by the OX Security report finding 15,465 publicly indexed MCP servers, many on home machines via ngrok-style tunnels.

## How it works
1. User provides a hostname or URL where they run an MCP server
2. Scanner checks:
   - DNS resolution and whether it points to a residential/dynamic IP range
   - Whether the host responds on common MCP ports
   - Whether the server identifies itself as MCP (via well-known endpoints or banners)
   - Whether it's behind a consumer tunnel (ngrok, Cloudflare Tunnel, etc. via CNAME/hostname patterns)
3. Returns a verdict:
   - **Exposed**: Publicly reachable MCP server, no access control detected
   - **Tunnel**: Behind a consumer tunnel, reachable but obscured
   - **Not found**: No MCP server detected at this address
   - **Clean**: Server found but properly restricted (auth, IP allowlist, etc.)

## Verdict wording (never "safe")
- Best case: "No publicly exposed MCP server found at this address."
- With caveats: list what was checked and the limitations.

## Implementation notes
- Runs as a new check in the existing free scanner
- No TI corpus dependency for the exposure check itself
- If an exposed server is found, offer the MCP Proxy Firewall as the fix (screen in front of it)
- Rate limit to prevent abuse as a port scanner

## Marketing angle
"15,465 MCP servers are exposed to the internet right now. Is yours one of them?" Free check, no signup.
