FROM python:3.12-slim

WORKDIR /app

# Build relayshield-mcp from this repo's own source, not a possibly-stale
# PyPI release -- the root Dockerfile pins an old published version for a
# different use case (a plain stdio container); this one always ships
# whatever is on this branch.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Proxy/runtime deps for wrapping the stdio server over Streamable HTTP.
# apify>=2,<3 (and the crawlee 0.6.x it pulls in) crashes on import against
# the pydantic version fastmcp requires -- crawlee's HttpHeaders model hits
# "cannot specify both default and default_factory". apify>=4,<5 pulls in
# crawlee>=1.x, which is built against current pydantic and actually imports.
# Verified 2026-08-25: apify>=2,<3 crash-loops 100% of real Standby runs.
RUN pip install --no-cache-dir "fastmcp>=3,<4" "apify>=4,<5" "uvicorn>=0.30"

COPY .actor/src ./actor_src

# RELAYSHIELD_API_URL must not be declared as an empty string here: main.py
# does os.environ.get("RELAYSHIELD_API_URL", "https://api.relayshield.net"),
# and .get()'s fallback only fires when the key is absent, not when it's set
# to "". An empty ENV line here silently wins over that fallback and every
# tool call fails with "RELAYSHIELD_API_URL environment variable must be
# set" -- confirmed live 2026-08-25. Set the real default directly instead;
# override in Apify Console only if pointing at a different API deployment.
ENV RELAYSHIELD_API_URL="https://api.relayshield.net"
ENV RELAYSHIELD_API_KEY=""
ENV RELAYSHIELD_X_PAYMENT=""

CMD ["python", "actor_src/main.py"]
