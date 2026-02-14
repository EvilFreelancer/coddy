FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt update \
 && apt install -y --no-install-recommends git curl openssh-client \
 && rm -rf /var/lib/apt/lists/*

# Install Cursor CLI (agent binary) for the worker
RUN curl -fsSL https://cursor.com/install | bash \
 && cp /root/.local/bin/agent /usr/local/bin/agent 2>/dev/null || true

# Copy project and install
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Cooy soures
COPY coddy/ ./coddy/

# Create non-root user
RUN useradd -m -u 1000 coddy && chown -R coddy:coddy /app
USER coddy

# Health check for daemon (HTTP server on 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Default: run daemon (webhook server). Override with "worker" in compose.
CMD ["python", "-m", "coddy", "observer"]
