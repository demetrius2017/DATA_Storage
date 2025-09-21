# PostgreSQL OrderBook Data Collector
# Production Docker image for real-time WebSocket data collection

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    postgresql-client \
    curl \
    wget \
    git \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Create application user and directory
RUN useradd -m -u 1000 collector && \
    mkdir -p /app /app/logs /app/data && \
    chown -R collector:collector /app

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY collector/ ./collector/

# Set ownership for all app files
RUN chown -R collector:collector /app

# Switch to non-root user
USER collector

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Expose monitoring port
EXPOSE 8000

# Default command
CMD ["python3", "collector/scripts/docker_entrypoint.py"]