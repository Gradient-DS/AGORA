FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY common/ ./common/
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "agora_openai.api.server"]

