FROM python:3.11-slim

LABEL maintainer="arbitrage_monitor"
LABEL description="Personal Financial Arbitrage Monitoring System"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/config

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sqlite3; conn = sqlite3.connect('data/monitor_history.db'); conn.execute('SELECT 1'); conn.close()" || exit 1

CMD ["python", "core_scheduler.py"]
