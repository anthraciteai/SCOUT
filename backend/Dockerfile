FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps useful for document parsing / OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-docling.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Docling is heavy (pulls torch, etc.). Install best-effort so the image
# still builds if it fails; the app falls back to lightweight extractors.
ARG INSTALL_DOCLING=true
RUN if [ "$INSTALL_DOCLING" = "true" ]; then \
      pip install -r requirements-docling.txt || echo "WARN: docling install failed, using fallback extractors"; \
    fi

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
