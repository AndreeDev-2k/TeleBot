# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 1) Tạo folder và user
RUN mkdir -p /ms-playwright && \
    useradd --create-home appuser

# 2) Cài deps hệ thống (cả Playwright/chromium)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates libnss3 libxss1 libasound2 \
      libatk1.0-0 libgtk-3-0 libx11-xcb1 libxcomposite1 \
      libxdamage1 libxrandr2 libgbm1 libcups2 libdrm2 \
      libxcb1 libxtst6 build-essential libpq-dev python3-dev \
      libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3) Cài Python deps + Playwright
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python3 -m playwright install chromium

# 4) Copy code, chuyển quyền
COPY --chown=appuser:appuser . .
USER appuser

CMD ["bash", "scripts/start_services.sh"]

