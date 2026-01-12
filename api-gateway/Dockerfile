FROM python:3.11-slim

WORKDIR /app

# Copy all source files first
COPY pyproject.toml .
COPY src/ src/

# Install the package (now that src/ exists)
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["python", "-m", "api_gateway.main"]
