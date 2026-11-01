FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download required NLTK datasets for offline summarization
RUN python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)"

# Copy application files
COPY . .

# Persistent crypto state (sealed HE context, ciphertext vault, audit log) lives on a volume.
RUN mkdir -p /data/he /data/audit && chmod 700 /data/he /data/audit
VOLUME ["/data"]

EXPOSE 8000

# HOST/PORT come from the environment. docker-compose.yml sets HOST=127.0.0.1 so that, with host
# networking, the API is reachable only through Nginx on :443 and never directly from the LAN.
CMD ["sh", "-c", "exec uvicorn main:app --host \"${HOST:-0.0.0.0}\" --port \"${PORT:-8000}\""]
