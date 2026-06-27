# Pinned by digest for reproducible, supply-chain-safe builds (OpenSSF Scorecard).
# This is python:3.11-slim; refresh the digest periodically with: docker pull python:3.11-slim
FROM python:3.11-slim@sha256:cdbd05fb6f457ca275ff51ce00d93d865ca0b6a25f5ffb08262d94f6835771e5

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces expects port 7860
EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
