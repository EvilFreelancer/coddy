FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt update \
 && apt install -y --no-install-recommends git curl nodejs \
 && ln -sf /usr/bin/nodejs /usr/local/bin/node \
 && rm -rf /var/lib/apt/lists/*

# Copy project and install (package coddy at repo root)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY coddy/ ./coddy/
COPY tests/ ./tests/

# Install Cursor CLI (agent binary)
RUN curl -fsSL https://cursor.com/install | bash \
 && cp /root/.local/bin/agent /usr/local/bin/agent

# Create non-root user
RUN useradd -m -u 1000 coddy && chown -R coddy:coddy /app
USER coddy

# Health check (no extra deps)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Run application
CMD ["python", "-m", "coddy.main"]
