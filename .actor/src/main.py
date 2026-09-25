"""
Apify Actor entrypoint for relayshield-mcp, run in Standby mode.

This does NOT reimplement the MCP server. relayshield_mcp.server is the
same stdio-transport server used by Claude Desktop and every other MCP
client -- unchanged. This wraps it with a FastMCP proxy that spawns it as a
subprocess and re-exposes it over Streamable HTTP at /mcp, which is what
Apify's Standby mode expects (see .actor/actor.json's webServerMcpPath).
Adding a tool to relayshield_mcp.server therefore shows up here for free;
there is nothing in this file to keep in sync with the tool list.

RELAYSHIELD_API_KEY / RELAYSHIELD_X_PAYMENT are read from this Actor's own
environment (set as Actor input / env vars in Apify Console), not from the
calling agent -- Apify bills the agent for the Actor run; RelayShield bills
through whichever of those two is configured here.
"""

import asyncio
import os

import uvicorn
from apify import Actor
from fastmcp.server import create_proxy

RELAYSHIELD_API_URL = os.environ.get("RELAYSHIELD_API_URL", "https://api.relayshield.net")


async def main() -> None:
    async with Actor:
        proxy = create_proxy(
            {
                "mcpServers": {
                    "relayshield": {
                        "command": "relayshield-mcp",
                        "args": [],
                        "env": {
                            "RELAYSHIELD_API_URL": RELAYSHIELD_API_URL,
                            "RELAYSHIELD_API_KEY": os.environ.get("RELAYSHIELD_API_KEY", ""),
                            "RELAYSHIELD_X_PAYMENT": os.environ.get("RELAYSHIELD_X_PAYMENT", ""),
                        },
                    }
                }
            },
            name="relayshield-mcp-proxy",
        )
        app = proxy.http_app(path="/mcp", transport="streamable-http")

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=Actor.configuration.web_server_port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        # Standby mode keeps this Actor run alive to serve requests rather
        # than exiting after one task -- this just runs until Apify stops it.
        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
