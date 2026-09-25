FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir relayshield-mcp
ENV RELAYSHIELD_API_URL=""
ENV RELAYSHIELD_API_KEY=""
ENV RELAYSHIELD_X_PAYMENT=""
CMD ["relayshield-mcp"]
