FROM python:3.11-slim

# stdout без буфера — логи structlog через PrintLoggerFactory идут немедленно;
# без .pyc — не нужны в контейнере; pip не кэшируем — экономим слой
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Непривилегированный пользователь — сервис не должен работать от root
RUN adduser --disabled-password --gecos "" appuser

# Зависимости в отдельном слое: пересобирается только при изменении requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Исходники — второй слой, меняется чаще
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8080

# /api/v1/health всегда 200 (даже без бэкендов — в теле "offline") — безопасно для проверки
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=2).status==200 else 1)"

# uvicorn CLI как PID 1 — корректный SIGTERM; reload выключен (dev-only, в main.py __main__)
# --no-access-log: фикс дублирующихся логов (main.py:163 отключает только при python main.py)
# --proxy-headers: за nginx client_ip из X-Forwarded-For, иначе всегда 127.0.0.1
# --forwarded-allow-ips=*: безопасно, т.к. compose мапит только на 127.0.0.1:8080
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--no-access-log", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
