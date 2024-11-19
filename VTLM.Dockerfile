FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libasound2-dev \
    libportaudio2 \
    portaudio19-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY ./requirements-plain.txt /app
RUN pip install --no-cache-dir -r requirements-plain.txt
RUN pip install --no-cache-dir torch torchvision torchaudio
COPY . .
EXPOSE 8765
CMD ["python", "vttllm", "main.py"]
