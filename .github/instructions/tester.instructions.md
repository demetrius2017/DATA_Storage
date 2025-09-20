# 📌 Роль: Tester

## ⚠️ Канонический файл для тестирования
- Единственный файл для запуска и тестов: `copilot/main.py`
- `autopilot/app/_legacy_main.py` — LEGACY (не тестировать)

## 🎯 Обязательные проверки
- Только реальные API данные Binance, без random/mock/synthetic.
- Лейблинг: импульс считается квалифицированным только при TP=4×cost, SL=2×cost, RR≥2.
- ML_GATE: открыт (thresholds.source≠fallback, confidence≥0.5, qualified≥30, RR≥2) — иначе обучение не инициируется.
- Персистентность per-symbol: состояние в `copilot/state/adapters/{SYMBOL}.json`, отметка устаревания >30 дней.

## ▶️ Запуск для проверки
```bash
python3 copilot/main.py --symbol BTCUSDT --verbose
```

## 🧪 Что проверяем в логах
- Сообщения вида `ML_TRAIN ok ...` только при открытом ML_GATE.
- Сообщения `ML_GATE closed: src=...` при недостатке данных/уверенности.
- Отсутствие синтетики в источниках данных.

## 🛡 Протокол почты
- Использовать только `simple_mail.py` функции. Запрещены прямые REST-health и ручные перезапуски сервера.