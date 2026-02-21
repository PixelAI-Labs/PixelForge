# PixelForge Backend Dockerfile  –  GPU-only (NVIDIA CUDA)
FROM nvidia/cuda:12.6.3-devel-ubuntu24.04 AS base

# Prevent interactive prompts during apt
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System deps: Python 3.12 (default on Ubuntu 24.04), build tools for bcrypt/Pillow, OpenCV headless libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev python3-pip \
        build-essential libffi-dev libjpeg-dev libpng-dev \
        libgl1 libglib2.0-0 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch with CUDA 12.6 first (must come before requirements.txt
# so pip doesn't pull the CPU-only wheel from PyPI).
RUN pip install --no-cache-dir --break-system-packages \
        torch torchvision --index-url https://download.pytorch.org/whl/cu126

# Now install remaining Python deps (torch is already satisfied)
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

# GPU host: load models at startup
ENV PIXELFORGE_SKIP_LOAD=0
ENV PIXELFORGE_JWT_SECRET=change-me-in-production
# Tell HuggingFace to cache models inside the container volume
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
