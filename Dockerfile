# Dockerfile для Binance OrderBook Collector
FROM python:3.11-slim

# Метадата
LABEL maintainer="demetrius2017@gmail.com"
LABEL description="Binance OrderBook Data Collector for Digital Ocean"
LABEL version="2.0.0"

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование requirements первым для кеширования слоев
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY collector/ ./collector/
COPY api/ ./api/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY *.md ./
COPY *.py ./

# Создание пользователя для безопасности (не root)
RUN useradd -m -u 1000 collector && \
    chown -R collector:collector /app && \
    mkdir -p /app/logs && \
    chown -R collector:collector /app/logs

# Переключение на пользователя collector
USER collector

# Открытие портов
EXPOSE 8080 9091

# Health check для контейнера
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import psutil; exit(0 if len(psutil.pids()) > 1 else 1)" || exit 1

# Точка входа
ENTRYPOINT ["python", "-m"]

# Команда по умолчанию (можно переопределить в docker-compose)
CMD ["collector.main", "--production", "--symbols", "BTCUSDT", "ETHUSDT"]