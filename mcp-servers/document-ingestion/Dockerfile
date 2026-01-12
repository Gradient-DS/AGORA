FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pdf2image and docling
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-nld \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Note: paths are relative to build context (mcp-servers/), not Dockerfile location
COPY document-ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ingestion code
COPY document-ingestion/ .

# Create output directories
RUN mkdir -p output/markdown output/chunks

# Default Weaviate URL for Docker network
ENV MCP_WEAVIATE_URL=http://weaviate:8080
ENV MCP_EMBEDDING_PROVIDER=openai
ENV PYTHONUNBUFFERED=1

CMD ["python", "ingest.py"]
