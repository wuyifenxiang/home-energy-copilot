# Self-hosted Alexa+ MCP add-on.
#
# The image contains no third-party Python packages: the MCP Streamable HTTP
# transport is implemented in the standard library, so the build needs no
# network access beyond the base image.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Home Energy Copilot" \
      org.opencontainers.image.description="Self-hosted MCP server for the Alexa+ track, Amazon Developer Hackathon 2026" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALEXA_MCP_PEAK_WINDOW=17:00-21:00

WORKDIR /app

# Source only. There are no requirements to install.
COPY alexa_mcp/ /app/alexa_mcp/
COPY tests/ /app/tests/
COPY scripts/ /app/scripts/
COPY README.md LICENSE /app/

# Run as a non-root user with a writable state directory.
RUN useradd --create-home --uid 10001 copilot \
    && mkdir -p /app/data \
    && chown -R copilot:copilot /app
USER copilot

# Keep the demo state on a volume so restarts are reproducible.
VOLUME ["/app/data"]

EXPOSE 8765

# Inside a container we must bind beyond loopback for the port to be reachable.
# Put TLS and authentication in front of this before exposing it publicly; the
# MCP specification recommends authentication for all remote connections.
ENTRYPOINT ["python", "-m", "alexa_mcp"]
CMD ["--host", "0.0.0.0", "--port", "8765", "--db", "/app/data/home.db"]

# The health endpoint reports status, protocol revision, and the tool surface.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4).status == 200 else 1)"
