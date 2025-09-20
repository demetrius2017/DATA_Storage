# 📌 Роль: Developer

## ⚠️ ВАЖНО: Канонический корень проекта
- Весь активный код и тесты находятся в папке `copilot/`
- Основной исполняемый файл (единственный entrypoint): `copilot/main.py`
- `autopilot/app/_legacy_main.py` — LEGACY (не запускать)
- Все пути указываем с префиксом `copilot/`

## 📚 ОБЯЗАТЕЛЬНО ПРОЧИТАТЬ
- `PROJECT_SIMPLE_LOGIC_CANVAS.md`
- `copilot/docs/cross_symbol_architecture.md` (единый backbone + per-symbol adapters)

## ⚡ ОСНОВНЫЕ ПРАВИЛА
- Только реальные данные Binance. Запрет random/mock/synthetic.
- Отбор обучающих событий: только подтверждённые сильные импульсы (TP=4×cost, SL=2×cost, RR≥2).
- ML_GATE открыт, если: thresholds.source≠fallback, накоплено достаточно размеченных импульсов (`--min-labeled`), RR≥2.0. Требование confidence≥0.5 снято.
- Персистентность: хранить лёгкое состояние адаптера per-symbol, устаревание >30 дней.

## 🎯 DEV-СПРИНТ 1 (минимальный инкремент)
1) Фичи
- Реализовать извлечение time-context и символ-эмбеддинга.
- Подготовить интерфейсы для MM-эмбеддинга (метрики поведения MM без синтетики).

2) Тренер
- Онлайн-тренер в `copilot/training/online_trainer.py` с lookahead-валидацией TP/SL и ML_GATE.
- Добавлен подсчёт `labeled_count` и метод `record_labeled_sample()` для фазы разметки.

3) Адаптеры
- `copilot/persistence/adapter_store.py` (JSON-хранилище в `copilot/state/adapters/`).
- Сохранение состояния после обучения и во время разметки, загрузка на старте.

4) Интеграция
- Прокинуть symbol из CLI в тренер. Логи ML_GATE оставить как в проде.

## 🖥️ LIVE‑мониторинг Runtime
- Шина состояния: `copilot/monitor/runtime_bus.py` — потокобезопасная, с файловым дампом (`copilot/state/runtime_state.json`), содержит короткую `price_history`.
- Веб‑UI: `copilot/monitor/streamlit_app.py` — читает JSON‑состояние и отображает метрики и графики.

Запуск:
```bash
# 1) Основной процесс
python3 copilot/main.py --symbol TRUMPUSDT --lookahead 120 --min-labeled 10 --verbose

# 2) UI мониторинг
streamlit run copilot/monitor/streamlit_app.py --server.port 8501
```

## ▶️ Запуск (канонично)
```bash
python3 copilot/main.py --symbol BTCUSDT
```

## 🛠️ Инструменты

**Все остальные детали в lean-инструкциях и справочной карточке!**
## 🔥 Активный фокус (feature/tardis-replay)
- Реплей-оценка студентов на окне не более 1 часа с выравниванием по пивотам (anti‑leakage исправлен).
- Паритет фич между обучением и инференсом; при реплее по trades — исключение/прокси для `spread_bps`.
- Корректировки обучения: логрег с L2 и class_weight; упрощённый MLP с weight decay; порог‑свип и калибровка вероятностей.
- Корректировка разметки импульсов: критерии значимости/протяжённости, фазовый контекст, возможные многогоризонтные метки. Строгий anti‑leak.
- Задача подробно: `copilot/tasks/2025-08-19_students_training_corrections.md`.
