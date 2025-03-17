# Base image
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

USER root

# Install required system packages
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

# Create a user and group for the application
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set working directory and permissions
WORKDIR /app
RUN mkdir -p /app/logs /app/models && chown -R appuser:appgroup /app

# Switch to appuser for security
USER appuser

# Copy Python dependencies
COPY ./requirements-plain.txt /app/

# Convert encoding if necessary
USER root
RUN iconv -f utf-16le -t utf-8 /app/requirements-plain.txt -o /app/requirements-plain-utf8.txt || true && \
    mv /app/requirements-plain-utf8.txt /app/requirements-plain.txt

# Setup environment variables
USER appuser
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PIP_CACHE_DIR="/tmp/.pip-cache"
ENV HF_HOME="/app/models"

# Install Python dependencies
USER root
RUN mkdir -p /home/appuser/.local /tmp/.pip-cache && chown -R appuser:appgroup /home/appuser /tmp/.pip-cache
USER appuser
RUN pip install --upgrade pip && \
    pip install fastavro && \
    pip install boto3 chromadb elastic-apm langchain minio ollama langchain-community && \
    pip install -r requirements-plain.txt && \
    pip install sentencepiece torch torchaudio torchvision weaviate-client==3.*

# Copy application code
COPY ./llm_run_server.py /app/
COPY ./jsonSerializer /app/jsonSerializer
COPY ./schemas /app/schemas

# Set the log file environment variable
ENV LOG_FILE="/app/logs/llm_server.log"

# Default command
CMD ["python", "llm_run_server.py"]
