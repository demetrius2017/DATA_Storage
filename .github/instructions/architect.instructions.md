# 📌 Роль: Architect

## Канонические пути
- Active root: `copilot/`
- Entry point: `copilot/main.py`
- Legacy: `autopilot/app/_legacy_main.py` (не запускать)

## Задачи
- Контроль соответствия RULES: real data only, TP=4×cost/SL=2×cost, ML_GATE критерии.
- Ведение документа `copilot/docs/cross_symbol_architecture.md`.
- Контроль персистентности per-symbol и политики устаревания >30 дней.

## Коммуникации
- Все уведомления через почтовую систему, без прямых REST-health.