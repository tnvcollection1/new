# ✅ Uses Playwright's official image with Chromium & OS deps preinstalled
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

# Optional: keep Python output unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app
COPY app ./app

# Render sets $PORT; bind to it
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
