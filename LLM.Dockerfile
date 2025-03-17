# Base image
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

USER root

# Install system packages
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gcc \
    libasound2-dev \
    libavcodec-dev \
    libavformat-dev \
    libportaudio2 \
    libswscale-dev \
    lsb-release \
    portaudio19-dev \
    python3-dev \
    telnet \
    wget && \
    rm -rf /var/lib/apt/lists/*

# Create app user/group
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set up workspace
WORKDIR /app
RUN mkdir -p /app/logs /app/models && chown -R appuser:appgroup /app

# Copy requirements file and fix encoding
COPY ./requirements-plain.txt /app/
RUN iconv -f utf-16le -t utf-8 /app/requirements-plain.txt -o /app/requirements-plain-utf8.txt || true && \
    mv /app/requirements-plain-utf8.txt /app/requirements-plain.txt

# Set environment variables
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PIP_CACHE_DIR="/tmp/.pip-cache"
ENV HF_HOME="/app/models"

# Install Python dependencies
RUN mkdir -p /home/appuser/.local /tmp/.pip-cache && \
    chown -R appuser:appgroup /home/appuser /tmp/.pip-cache
USER appuser
RUN pip install --upgrade pip && \
    pip install fastavro && \
    pip install boto3 chromadb elastic-apm fastavro langchain minio ollama langchain-community && \
    pip install -r requirements-plain.txt && \
    pip install sentencepiece torch torchaudio torchvision weaviate-client==3.*

# Copy application code with explicit ownership
USER root
COPY ./llm_run_server.py /app/
COPY ./jsonSerializer /app/jsonSerializer
COPY ./schemas /app/schemas
RUN chown -R appuser:appgroup /app/llm_run_server.py /app/jsonSerializer /app/schemas
USER appuser

# Final setup
ENV LOG_FILE="/app/logs/llm_server.log"
CMD ["python", "llm_run_server.py"]