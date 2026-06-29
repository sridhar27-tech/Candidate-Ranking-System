# --- Stage 1: C++ Extension Builder ---
FROM python:3.12-slim as cpp-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN pip install --no-cache-dir pybind11 setuptools wheel

# Copy source code files required to compile the native module
COPY ./src ./src
COPY compile.py .
RUN python compile.py

# --- Stage 2: Clean System Runtime ---
FROM python:3.12-slim as runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ingest requirement profiles and cache them inside the layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Retrieve the compiled C++ shared object module directly from stage 1
COPY --from=cpp-builder /build/cpp_ranker*.so .

# Copy your core application architecture
COPY . .

# Ensure standard model files are pre-downloaded during image build cycles
# This avoids networking issues or download delays during live evaluation runs
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]