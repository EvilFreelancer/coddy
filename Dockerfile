FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt update \
 && apt install -y --no-install-recommends git curl \
 && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY src/ ./src/
COPY tests/ ./tests/

# Create non-root user
RUN useradd -m -u 1000 coddy && chown -R coddy:coddy /app
USER coddy

# Health check (no extra deps)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Run application
CMD ["python", "-m", "coddy.main"]
