FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
# Thiết lập PYTHONPATH để Python tìm src/ làm root của package
ENV PYTHONPATH=/app/src

# Tạo user không phải root
RUN useradd --create-home appuser

# Cài thư viện hệ thống
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      python3-dev \
      libxml2-dev \
      libxslt-dev && \
    rm -rf /var/lib/apt/lists/*

# Đặt thư mục làm việc
WORKDIR /app

# Copy và cài dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt

# **Quan trọng**: Copy toàn bộ source code vào container
COPY --chown=appuser:appuser . .

# Chuyển sang non-root user
USER appuser

# Lệnh khởi động
CMD ["bash", "scripts/start_services.sh"]


