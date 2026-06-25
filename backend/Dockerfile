# ============================================================================
# Multi-stage Dockerfile for RedRob AI Recruiter Backend
# Implements Inverted Cascade Funnel with C++ Ranker + FastAPI + Ollama Client
# ============================================================================

# ── Stage 1: Build C++ Extension Module ────────────────────────────────────
FROM python:3.12-slim as cpp-builder

WORKDIR /build

# Install build dependencies for C++ compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy only what's needed for C++ build
COPY requirements.txt .
COPY src/ ./src/
COPY compile.py .

# Install Python build dependencies
RUN pip install --no-cache-dir pybind11 setuptools wheel

# Compile the C++ ranker module
RUN python compile.py

# ── Stage 2: Runtime Image with Backend Application ────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy compiled C++ extension from builder stage
COPY --from=cpp-builder /build/cpp_ranker*.so ./

# Copy application source
COPY main.py .
COPY app/ ./app/

# Create data directory for candidate.jsonl
RUN mkdir -p data

# Pre-download sentence-transformers model at build time to avoid runtime delays
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Expose FastAPI port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run with uvicorn — use 4 workers for production throughput
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
