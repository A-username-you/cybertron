FROM python:3.12-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libssl-dev libmagic1 libcapstone4 \
    radare2 nmap && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN pip install --no-cache-dir build && python -m build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 libcapstone4 radare2 nmap && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl
COPY configs/ /app/configs/
COPY wordlists/ /app/wordlists/
EXPOSE 8000
ENTRYPOINT ["cybertron"]
CMD ["--help"]
