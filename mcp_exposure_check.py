"""
Exposed MCP Server Scanner Check.

Free check: "Is this MCP server exposed to the public internet?"
Inspired by OX Security's finding of 15,465 publicly indexed MCP servers.

Usage:
    python3 mcp_exposure_check.py <hostname-or-url>

Returns JSON with verdict and details.
"""

import json
import re
import socket
import sys
import urllib.parse
import urllib.request

# Consumer tunnel hostname patterns
TUNNEL_PATTERNS = [
    r"\.ngrok\.io$",
    r"\.ngrok-free\.app$",
    r"\.trycloudflare\.com$",
    r"\.cfargotunnel\.com$",
    r"\.localtunnel\.me$",
    r"\.serveo\.net$",
    r"\.bore\.pub$",
]

# Common MCP server ports to check
MCP_PORTS = [13508, 3000, 8080, 8000, 5000]

# Residential/dynamic IP ranges (simplified - real implementation would use a GeoIP DB)
# These are examples; a production version would check against known residential ASNs
RESIDENTIAL_HINTS = [
    "cable", "dsl", "fiber", "residential", "dynamic", "pool",
    "dhcp", "broadband", "home",
]


def check_tunnel(hostname):
    """Check if hostname matches known consumer tunnel patterns."""
    for pattern in TUNNEL_PATTERNS:
        if re.search(pattern, hostname, re.IGNORECASE):
            return pattern.strip("$\\.")
    return None


def check_port_open(host, port, timeout=3):
    """Check if a TCP port is open."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_mcp_endpoint(host, port, timeout=5):
    """Check if an MCP server responds on the given host:port."""
    # Try common MCP well-known paths
    paths = ["/mcp", "/.well-known/mcp", "/"]
    for path in paths:
        url = f"http://{host}:{port}{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-Scanner/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(4096).decode("utf-8", errors="ignore")
                headers = dict(resp.headers)
                # Look for MCP identifiers
                if any(marker in body.lower() for marker in ["mcp", "modelcontextprotocol", "json-rpc"]):
                    return {"path": path, "status": resp.status, "mcp_detected": True}
                # Check headers for MCP
                if any("mcp" in k.lower() for k in headers):
                    return {"path": path, "status": resp.status, "mcp_detected": True}
                return {"path": path, "status": resp.status, "mcp_detected": False}
        except Exception:
            continue
    return None


def scan(target):
    """Run the exposure check on a hostname or URL."""
    # Parse target
    if "://" not in target:
        target = "http://" + target
    parsed = urllib.parse.urlparse(target)
    hostname = parsed.hostname or target
    port = parsed.port

    result = {
        "target": target,
        "hostname": hostname,
        "checks": {},
        "verdict": "unknown",
        "details": [],
    }

    # Check 1: Tunnel detection
    tunnel = check_tunnel(hostname)
    result["checks"]["tunnel"] = tunnel
    if tunnel:
        result["details"].append(f"Hostname matches consumer tunnel pattern: {tunnel}")

    # Check 2: DNS resolution
    try:
        ip = socket.gethostbyname(hostname)
        result["checks"]["resolves"] = ip
        result["details"].append(f"Resolves to {ip}")
    except socket.gaierror:
        result["checks"]["resolves"] = None
        result["verdict"] = "not_found"
        result["details"].append("Hostname does not resolve")
        return result

    # Check 3: Port scan for MCP
    ports_to_check = [port] if port else MCP_PORTS
    open_ports = []
    mcp_found = None

    for p in ports_to_check:
        if check_port_open(hostname, p):
            open_ports.append(p)
            mcp_info = check_mcp_endpoint(hostname, p)
            if mcp_info and mcp_info.get("mcp_detected"):
                mcp_found = {"port": p, **mcp_info}
                break

    result["checks"]["open_ports"] = open_ports
    result["checks"]["mcp_detected"] = mcp_found

    # Determine verdict
    if mcp_found:
        if tunnel:
            result["verdict"] = "tunnel"
            result["details"].append(
                f"MCP server detected on port {mcp_found['port']} behind consumer tunnel. "
                "Reachable but obscured. Consider restricting access."
            )
        else:
            result["verdict"] = "exposed"
            result["details"].append(
                f"MCP server publicly reachable on port {mcp_found['port']} with no tunnel. "
                "This server is directly exposed to the internet."
            )
    elif open_ports:
        result["verdict"] = "not_found"
        result["details"].append(
            f"Open ports found ({', '.join(map(str, open_ports))}) but no MCP server detected."
        )
    else:
        result["verdict"] = "clean"
        result["details"].append("No publicly exposed MCP server found at this address.")

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mcp_exposure_check.py <hostname-or-url>", file=sys.stderr)
        sys.exit(1)

    result = scan(sys.argv[1])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
