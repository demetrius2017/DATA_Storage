# 🚀 Quick Start Guide - OrderBook Collector на Digital Ocean

## 📋 Предварительные требования

1. **Digital Ocean Account** с активной картой
2. **Binance API ключи** (только для чтения данных)
3. **SSH ключ** для доступа к серверу
4. **Локальная машина** с Git и SSH клиентом

## ⚡ 5-минутный запуск

### Шаг 1: Создание инфраструктуры на Digital Ocean

```bash
# 1. Создайте Droplet (Ubuntu 22.04, 4GB RAM, 2 vCPU)
# 2. Создайте Managed PostgreSQL Database (Basic Plan, 1GB RAM)
# 3. Добавьте ваш SSH ключ к Droplet
```

### Шаг 2: Локальная подготовка

```bash
# Клонируйте репозиторий
git clone https://github.com/demetrius2017/DATA_Storage.git
cd DATA_Storage

# Сделайте скрипты исполняемыми
chmod +x manage.sh
chmod +x scripts/deploy_digital_ocean.sh
```

### Шаг 3: Конфигурация

```bash
# Запустите менеджер (создаст файл конфигурации)
./manage.sh deploy

# Отредактируйте конфигурацию
nano config/deploy.conf
```

**Заполните в `config/deploy.conf`:**
```bash
REMOTE_HOST="164.90.XXX.XXX"  # IP вашего Droplet
DB_HOST="your-cluster-do-user-123456-0.b.db.ondigitalocean.com"
DB_PASSWORD="your_password_here"
BINANCE_API_KEY="your_api_key"
BINANCE_SECRET_KEY="your_secret_key"
```

### Шаг 4: Развертывание

```bash
# Автоматическое развертывание
./manage.sh deploy
```

### Шаг 5: Проверка работы

```bash
# Проверить статус
./manage.sh status

# Посмотреть логи
./manage.sh logs

# Открыть мониторинг
./manage.sh monitor
```

## 🎯 Доступ к сервисам

После развертывания доступны:

| Сервис | URL | Назначение |
|--------|-----|-----------|
| **API** | `http://YOUR_IP:8080` | REST API для доступа к данным |
| **Grafana** | `http://YOUR_IP:3000` | Мониторинг и дашборды |
| **Prometheus** | `http://YOUR_IP:9090` | Метрики системы |

**Учетные данные Grafana:** `admin` / `admin123`

## 📊 Основные команды управления

```bash
# Статус системы
./manage.sh status

# Логи коллектора
./manage.sh logs collector

# Логи API
./manage.sh logs api

# Перезапуск сервисов
./manage.sh restart

# Масштабирование до 100 символов
./manage.sh scale 100

# Создание бэкапа
./manage.sh backup

# Остановка всех сервисов
./manage.sh stop
```

## 🔧 Настройка для продакшена

### Увеличение количества символов

```bash
# Постепенное масштабирование
./manage.sh scale 50   # Начать с 50 символов
./manage.sh scale 100  # Увеличить до 100
./manage.sh scale 200  # Полная нагрузка
```

### Мониторинг производительности

1. **Grafana Dashboard** - `http://YOUR_IP:3000`
   - CPU и Memory usage
   - Database connections
   - Message throughput
   - Error rates

2. **PostgreSQL Metrics**
   - Connection pool status
   - Query performance
   - Storage usage

3. **System Health**
   - Disk space
   - Network I/O
   - Container status

## 📈 API Endpoints

### Получение данных orderbook

```bash
# Текущее состояние BTCUSDT
curl http://YOUR_IP:8080/data/BTCUSDT

# Статистика системы
curl http://YOUR_IP:8080/stats

# Здоровье системы
curl http://YOUR_IP:8080/health

# Список доступных символов
curl http://YOUR_IP:8080/symbols
```

### Пример ответа API

```json
{
  "symbol": "BTCUSDT",
  "timestamp": 1703875200.123,
  "bids": [
    ["43500.00", "0.15"],
    ["43499.99", "0.25"]
  ],
  "asks": [
    ["43500.01", "0.20"],
    ["43500.02", "0.30"]
  ],
  "last_update_id": 1234567890
}
```

## 🛡️ Безопасность

### Firewall конфигурация

```bash
# Открыты только необходимые порты:
# 22   - SSH
# 8080 - API
# 3000 - Grafana
# 9090 - Prometheus
```

### PostgreSQL безопасность

- SSL соединения включены
- Connection pooling с лимитами
- Автоматические бэкапы
- Managed database от Digital Ocean

### API ключи

- Только READ-ONLY доступ к Binance
- Нет торговых операций
- Безопасное хранение в переменных окружения

## 📊 Ожидаемая нагрузка

| Параметр | Значение |
|----------|----------|
| **Символов** | 200 пар |
| **Сообщений/мин** | ~9,000 |
| **Данных/день** | ~400MB |
| **Данных/месяц** | ~12GB |
| **CPU Usage** | 30-50% |
| **Memory Usage** | 60-80% |

## 🔥 Troubleshooting

### Проблема: Контейнеры не запускаются

```bash
# Проверить логи
./manage.sh logs

# Проверить конфигурацию
ssh root@YOUR_IP "cat /opt/orderbook-collector/.env"

# Перезапустить с чистого листа
./manage.sh stop
./manage.sh start
```

### Проблема: Нет подключения к PostgreSQL

```bash
# Проверить настройки DB в .env файле
# Убедиться что IP Droplet добавлен в Trusted Sources PostgreSQL
# Проверить SSL сертификаты
```

### Проблема: Высокое потребление CPU

```bash
# Уменьшить количество символов
./manage.sh scale 50

# Проверить метрики в Grafana
./manage.sh monitor
```

## 💰 Стоимость инфраструктуры

| Компонент | Спецификация | Стоимость/месяц |
|-----------|--------------|-----------------|
| **Droplet** | 4GB RAM, 2 vCPU, 80GB SSD | $24 |
| **PostgreSQL** | 1GB RAM, 10GB Storage | $15 |
| **Backup Space** | 20GB | $2 |
| **Bandwidth** | 4TB | Включено |
| **Total** | | **~$41/месяц** |

## 📞 Поддержка

При возникновении проблем:

1. Проверьте статус: `./manage.sh status`
2. Посмотрите логи: `./manage.sh logs`
3. Откройте мониторинг: `./manage.sh monitor`
4. Создайте issue в GitHub репозитории

---

## 🎉 Поздравляем!

Ваш OrderBook Collector готов к работе в продакшене! 

Система будет собирать данные 24/7 и предоставлять их через REST API для ваших ML моделей.