# 🚨 ОБНОВЛЕННЫЕ ИНСТРУКЦИИ - LEAN VERSION

## 🧠 ВАЖНО: КОГНИТИВНАЯ ПЕРЕГРУЗКА ИСПРАВЛЕНА
**СТАРАЯ ВЕРСИЯ (234 строки) → НОВАЯ LEAN VERSION (50 строк)**

🎯 **ОБЯЗАТЕЛЬНО ЧИТАЙ НОВЫЕ ИНСТРУКЦИИ:**
`.github/instructions/developer_lean.instructions.md`

📋 **БЫСТРАЯ СПРАВКА:**  
`.github/instructions/DEVELOPER_QUICK_REFERENCE.md`

## 🛠️ ИСПОЛЬЗУЙ ИНСТРУМЕНТЫ КОНТРОЛЯ:
- `developer_workflow_assistant.py` - интерактивный помощник  
- `developer_auto_validator.py` - автоматическая проверка качества
- `developer_mail_test.py` - тест почтовой системы

## 📧 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ПОЧТОВОЙ СИСТЕМЫ:
**❌ ЗАПРЕЩЕНО:** `curl -X GET http://localhost:8080/mail/check`  
**❌ ЗАПРЕЩЕНО:** Любые REST API команды  
**✅ РАЗРЕШЕНО:** Только Python команды из simple_mail

### 🧪 СНАЧАЛА ЗАПУСТИ ТЕСТ ПОЧТЫ:
```bash
python3 developer_mail_test.py
```

### 📬 COPY-PASTE КОМАНДЫ ПОЧТЫ:
```bash
# 1. Проверить новые письма
python3 -c "from simple_mail import mail_check; print(mail_check('Developer'))"

# 2. Прочитать письмо (замени MSG_ID на реальный)
python3 -c "from simple_mail import mail_read; print(mail_read('Developer', 'MSG_ID'))"

# 3. Отправить отчет PM  
python3 -c "from simple_mail import mail_send; mail_send('Developer', 'PM', 'ГОТОВО', 'Детали + validation score')"

# 4. Архивировать задачу
python3 -c "from simple_mail import mail_done; mail_done('Developer', 'MSG_ID')"
```

## ⚡ ОСНОВНЫЕ ПРАВИЛА:
- **КОД РАБОТАЕТ ИЛИ НЕ РАБОТАЕТ** - никаких "почти готово"
- **ОБЯЗАТЕЛЬНАЯ ВАЛИДАЦИЯ:** `python3 developer_auto_validator.py` перед отчетом
- **ТОЛЬКО при score ≥ 95** можно отчитываться PM
- **НЕТ харкодов** BTCUSDT/ETHUSDT
- **НЕТ фейковых** random/return 0.0, 0.0

---
**Все остальные детали в lean-инструкциях и справочной карточке!**
