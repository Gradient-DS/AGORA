FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY regulation-analysis/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY regulation-analysis/server.py .
COPY document-ingestion/config.py ./config.py
COPY document-ingestion/database ./database
COPY document-ingestion/embeddings ./embeddings

RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

CMD ["python", "server.py"]
