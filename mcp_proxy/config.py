"""Configuration for the MCP proxy firewall.

All settings come from environment variables with sensible defaults.
"""

import os


class ProxyConfig:
    """Proxy configuration loaded from environment."""

    def __init__(self):
        # Upstream MCP server to forward clean requests to.
        # For HTTP upstream: full URL e.g. https://example.com/mcp
        self.upstream_url = os.environ.get("MCP_PROXY_UPSTREAM", "")

        # Port the proxy listens on.
        self.listen_port = int(os.environ.get("MCP_PROXY_PORT", "8090"))

        # Master switch for TI screening. When false, the proxy is a
        # pure passthrough (useful for debugging or trusted environments).
        self.screening_enabled = (
            os.environ.get("MCP_PROXY_SCREENING", "true").lower() != "false"
        )

        # RelayShield API base for TI screening calls.
        self.rs_api_base = os.environ.get(
            "RELAYSHIELD_API_URL",
            "https://api.relayshield.net",
        ).rstrip("/")

        # Optional API key. The composite-check endpoint is keyless, but a
        # key enables deeper checks (cached multi-vendor reports).
        self.rs_api_key = os.environ.get("RELAYSHIELD_API_KEY", "")

        # Screening timeout in seconds. If the TI check times out, the
        # call is allowed through (fail-open) and logged.
        self.screen_timeout = float(os.environ.get("MCP_PROXY_SCREEN_TIMEOUT", "5.0"))

        # Block on these verdict levels. "high" blocks only high-risk;
        # "medium" blocks high and medium. "unknown" never blocks.
        self.block_levels = os.environ.get("MCP_PROXY_BLOCK_LEVELS", "high,medium")

    @property
    def block_level_set(self) -> set:
        return {lvl.strip().lower() for lvl in self.block_levels.split(",")}

    def validate(self) -> list:
        """Return a list of configuration problems (empty if OK)."""
        problems = []
        if not self.upstream_url:
            problems.append("MCP_PROXY_UPSTREAM is not set")
        if self.listen_port < 1 or self.listen_port > 65535:
            problems.append(f"invalid port: {self.listen_port}")
        return problems
