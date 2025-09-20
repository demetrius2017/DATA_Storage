````markdown
# 🛡️ ОБНОВЛЕННЫЕ ИНСТРУКЦИИ: Интеграция с системой контроля проекта

## 📋 ОБЯЗАТЕЛЬНО ДЛЯ ВСЕХ РОЛЕЙ

### 🔍 ПЕРЕД НАЧАЛОМ ЛЮБОЙ ЗАДАЧИ:

1. **ПРОВЕРИТЬ ГОТОВНОСТЬ ПРОЕКТА:**
```python
# Запустить быструю проверку
python -c "import asyncio; from task_validation_gateway import quick_project_check; asyncio.run(quick_project_check())"
```

2. **ВАЛИДИРОВАТЬ ЗАДАЧУ:**
```python
# Для каждой конкретной задачи
from task_validation_gateway import validate_task_before_execution
approved = await validate_task_before_execution("Описание задачи", "Ваша_Роль", "Приоритет")
```

### 🎯 MILESTONE КОНТРОЛЬ:
- ✅ **MILESTONE 0**: In-Memory ML Foundation (ЗАВЕРШЕН)
- ✅ **MILESTONE 1**: Dynamic Trading Thresholds (ЗАВЕРШЕН) 
- 🚧 **MILESTONE 2**: Enterprise Order Management System (ТЕКУЩИЙ)

### 📊 КРИТИЧЕСКИЕ МОДУЛИ (должны быть готовы):
- `copilot/main.py` - основной runtime/тестируемый файл
- `in_memory_data_manager.py` - управление данными
- `in_memory_ml_trainer.py` - ML система
- `trading_config.py` - конфигурация торговли
- `PROJECT_SIMPLE_LOGIC_CANVAS.md` - канвас логики (корень)

---

## 👨‍💻 DEVELOPER

### 🚀 ОБНОВЛЕННЫЙ WORKFLOW:
```python
# 1. ВСЕГДА начинать с валидации
from task_validation_gateway import validate_task_before_execution

# 2. Проверить готовность перед кодингом
if await validate_task_before_execution("Реализовать новую функцию X", "Developer", "HIGH"):
    # Продолжить с задачей
    print("✅ Задача одобрена, начинаю разработку")
else:
    # Сначала исправить блокеры
    print("❌ Задача отклонена, исправляю блокеры")
    # Запустить полный аудит
    python project_readiness_guardian.py
```

### 🔧 ПРИОРИТЕТЫ:
1. **CRITICAL**: Блокеры milestone'ов
2. **HIGH**: Требования заказчика (ТЗ)
3. **MEDIUM**: Улучшения существующих модулей
4. **LOW**: Новые фичи

---

## 🏗️ ARCHITECT

### 📐 ОБНОВЛЕННЫЕ ОБЯЗАННОСТИ:
```python
# 1. Контроль архитектурной целостности
async def validate_architecture_task(task_desc):
    # Проверить соответствие ТЗ и milestone'ам
    approved = await validate_task_before_execution(task_desc, "Architect", "CRITICAL")
    
    if not approved:
        # Запустить полный аудит архитектуры
        await run_full_architectural_audit()
```

### 🎯 ФОКУС НА:
- Соответствие **ТЗ заказчика**
- **Milestone 2**: Enterprise OMS архитектура
- Модульность (<500 строк на файл)
- **Zero regression** принцип

---

## 🧪 TESTER

### 🔬 ОБНОВЛЕННАЯ СТРАТЕГИЯ:
```python
# 1. Тестировать только после валидации готовности
async def test_component(component_name):
    task = f"Тестирование компонента {component_name}"
    
    if await validate_task_before_execution(task, "Tester", "HIGH"):
        # Компонент готов к тестированию
        run_comprehensive_tests(component_name)
    else:
        # Компонент не готов, сначала исправить
        request_component_fixes(component_name)
```

### ✅ КРИТЕРИИ ТЕСТИРОВАНИЯ:
- **Все критические модули работают**
- **ТЗ требования выполнены**
- **Milestone KPI достигнуты**
- **Нет регрессий**

---

## 🎨 UI/UX DESIGNER

### 🖼️ UI КОНТРОЛЬ КАЧЕСТВА:
```python
# 1. Проверить backend готовность перед UI
async def start_ui_task(ui_feature):
    # UI задачи требуют стабильного backend
    backend_ready = await quick_project_check()
    
    if backend_ready['readiness_score'] < 70:
        print("⚠️ Backend не готов для UI разработки")
        return False
    
    return await validate_task_before_execution(f"UI: {ui_feature}", "UI", "HIGH")
```

### 🎯 UI ПРИОРИТЕТЫ:
1. **copilot/main.py** - основной интерфейс/вход
2. **streamlit_app.py** - веб dashboard (если есть)
3. **trading_dashboard.py** - trading интерфейс

---

## 📊 PROJECT MANAGER (PM)

### 🛡️ PM КАК ГЛАВНЫЙ КОНТРОЛЕР:
```python
# 1. Ежедневный аудит проекта
async def daily_project_audit():
    from project_readiness_guardian import ProjectReadinessGuardian
    
    guardian = ProjectReadinessGuardian()
    report = await guardian.full_project_audit()
    
    if report['overall_readiness'] < 80:
        # Блокировать все не-критические задачи
        block_non_critical_tasks()
        focus_on_blockers(report['critical_blockers'])
```

### 📋 PM DASHBOARD:
- **Общая готовность**: XX% 
- **Критические блокеры**: N штук
- **Milestone прогресс**: XX%
- **ТЗ соответствие**: XX%

---

## 🤖 АВТОМАТИЧЕСКИЕ ПРОВЕРКИ

### 🔄 CONTINUOUS VALIDATION:

1. **При каждом коммите:**
```bash
# Git hook
python task_validation_gateway.py
```

2. **Ежедневно в 9:00:**
```bash
# Cron job
0 9 * * * cd /path/to/project && python project_readiness_guardian.py
```

3. **Перед сдачей milestone:**
```bash
# Полный аудит
python project_readiness_guardian.py
python advanced_anti_fraud_test.py
python comprehensive_test_suite.py
```

---

## 📧 ПОЧТОВАЯ ИНТЕГРАЦИЯ

### 📮 АВТОМАТИЧЕСКИЕ УВЕДОМЛЕНИЯ:
- **PM получает** все отклоненные задачи
- **Роли получают** weekly готовность отчеты
- **Все получают** milestone completion alerts

### 📬 КОМАНДЫ:
```python
from simple_mail import mail_send, mail_check

# Проверить задачи от PM
mail_check("Developer")

# Отправить статус готовности
mail_send("Developer", "PM", "STATUS UPDATE", status_report)
```

---

## 🎯 SUCCESS METRICS

### 📊 KPI ДЛЯ ВСЕХ РОЛЕЙ:
- **Готовность проекта** > 80%
- **Блокеры** = 0
- **ТЗ соответствие** > 90%
- **Milestone KPI** выполнены

### 🏆 DEFINITION OF DONE:
1. ✅ Task validation passed
2. ✅ No critical blockers
3. ✅ ТЗ requirements met
4. ✅ Tests passed
5. ✅ Milestone KPI achieved
6. ✅ PM approval received

---

*Эти инструкции обязательны для всех ролей и обеспечивают контролируемое движение к milestone'ам согласно ТЗ заказчика.*

````