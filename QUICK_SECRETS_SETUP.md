# 🚀 Быстрая настройка GitHub Secrets

## 📍 Прямые ссылки для настройки

### 1. Перейти в настройки secrets:
```
https://github.com/demetrius2017/DATA_Storage/settings/secrets/actions
```

### 2. Кликнуть "New repository secret" для каждого секрета:

#### Обязательные секреты:

**SERVER_HOST**
```
Name: SERVER_HOST
Secret: your.server.ip.address
```

**SERVER_USER**  
```
Name: SERVER_USER
Secret: root
```

**POSTGRES_PASSWORD**
```
Name: POSTGRES_PASSWORD  
Secret: secure_db_password_2025
```

**SSH_PRIVATE_KEY**
```
Name: SSH_PRIVATE_KEY
Secret: -----BEGIN OPENSSH PRIVATE KEY-----
[вставить содержимое приватного SSH ключа]
-----END OPENSSH PRIVATE KEY-----
```

#### Опциональные для Binance API:

**BINANCE_API_KEY**
```
Name: BINANCE_API_KEY
Secret: your_binance_api_key_if_needed
```

**BINANCE_SECRET_KEY**
```
Name: BINANCE_SECRET_KEY  
Secret: your_binance_secret_key_if_needed
```

## 🔧 Генерация SSH ключа (если нужно)

```bash
# Генерация нового SSH ключа
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy

# Копирование публичного ключа на сервер
ssh-copy-id -i ~/.ssh/github_deploy.pub user@your.server.ip

# Вывод приватного ключа для копирования в GitHub Secret
cat ~/.ssh/github_deploy
```

## ✅ Проверка готовности

После добавления всех секретов:
1. Сделайте любой commit и push
2. Перейдите в Actions: https://github.com/demetrius2017/DATA_Storage/actions
3. Убедитесь что workflow запустился успешно
4. Проверьте деплой на сервере

## 🎯 Что произойдет после настройки

При следующем push в master:
1. 🔨 GitHub Actions соберет Docker образ
2. 📤 Загрузит в GitHub Container Registry
3. 🚀 Развернет на вашем сервере через SSH
4. ✅ Запустит health check
5. 📊 Начнет сбор данных с 200 символов MM анализа

---

💡 **Альтернатива:** Если у вас установлен GitHub CLI (`gh`), можете использовать команды:

```bash
gh secret set SERVER_HOST --body "your.server.ip"
gh secret set SERVER_USER --body "root"  
gh secret set POSTGRES_PASSWORD --body "secure_password"
```

Но SSH_PRIVATE_KEY все равно проще добавить через веб-интерфейс.