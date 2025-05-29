FROM python:3.10.8-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_NO_CACHE_DIR 1

# Install system dependencies including ffmpeg and other required tools
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    musl-dev \
    ffmpeg \
    aria2 \
    wget \
    curl \
    gnupg \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create downloads directory
RUN mkdir -p downloads

# Set proper permissions
RUN chmod +x /app/main.py

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

# Run the application
CMD ["python3", "main.py"]
