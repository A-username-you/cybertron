FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    libcapstone-dev libunicorn-dev \
    libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY configs/ ./configs/
COPY docker/entrypoint.sh ./
RUN chmod +x entrypoint.sh
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["./entrypoint.sh"]
