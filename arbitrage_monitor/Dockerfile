FROM python:3.11-slim

LABEL maintainer="arbitrage_monitor"
LABEL description="Personal Financial Arbitrage Monitoring System"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 默认使用官方 PyPI；受限网络可通过 --build-arg PIP_INDEX_URL=<镜像源> 覆盖
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/config

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sqlite3; conn = sqlite3.connect('data/monitor_history.db'); conn.execute('SELECT 1'); conn.close()" || exit 1

CMD ["python", "core_scheduler.py"]
