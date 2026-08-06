# --- vista/Dockerfile ---
# Build context should be the `vista/` directory (where manage.py lives).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System packages required by the OCR auto-fill pipeline and psycopg/Pillow:
#   tesseract-ocr, poppler-utils -> pytesseract / pdf2image
#   libgl1, libglib2.0-0         -> opencv-python-headless runtime import
#   curl                          -> container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]