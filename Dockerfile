FROM python:3.10.8-slim-buster

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    musl-dev \
    ffmpeg \
    aria2 \
    wget \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create necessary directories for bot operation
RUN mkdir -p ./downloads ./logs \
    && chmod 777 ./downloads ./logs

# Install yt-dlp for video downloading
RUN pip install --no-cache-dir yt-dlp

# Set environment variables for better performance
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=on

# Run as non-root user for security
RUN useradd -m -d /app appuser && chown -R appuser:appuser /app
USER appuser

# Start the bot
CMD ["python3", "main.py"]
