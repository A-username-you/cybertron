FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git gcc libmagic1 libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .
RUN pip install -e .

# Create data dirs
RUN mkdir -p /root/.cybertron /root/.cybertron/wordlists /root/.cybertron/tools

# Ports
EXPOSE 8443 8080

# Default: TUI (override with docker-compose)
CMD ["cybertron"]
