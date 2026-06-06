FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 for local docker-compose
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
