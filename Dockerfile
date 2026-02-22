FROM python:3.14-slim

WORKDIR /app

# Install system dependencies and Node.js 24 (Cursor agent needs Node 23.8+ for --use-system-ca)
RUN apt update \
 && apt install -y --no-install-recommends git curl openssh-client ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && (ln -sf /usr/bin/node /usr/local/bin/node 2>/dev/null || true)

# Copy project and install
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy sources
COPY coddy/ ./coddy/

# Create non-root user and install Cursor agent as coddy (so agent and index.js are under ~/.local)
RUN useradd -m -u 1000 coddy && chown -R coddy:coddy /app
USER coddy
RUN curl -fsSL https://cursor.com/install | bash
ENV PATH="/home/coddy/.local/bin:${PATH}"

# Health check for daemon (HTTP server on 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Default: run daemon (webhook server). Override with "worker" in compose.
CMD ["python", "-m", "coddy", "observer"]
