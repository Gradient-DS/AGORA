FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.32.0 \
    pydantic>=2.0.0

COPY mock_server.py .
COPY schemas/ ./schemas/

# Create mock_documents directory for report files
RUN mkdir -p mock_documents

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "mock_server.py"]
