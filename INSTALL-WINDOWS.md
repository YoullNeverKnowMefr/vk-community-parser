# Установка VK Parser на Windows Server

Инструкция для **Windows Server 2019 / 2022** (подходит и для Windows 10/11).

Скрипт работает **полностью через Playwright** (Chromium): вход в VK, чтение стены сообществ и публикация в канал — без API и без внешнего сервера токенов.

Копируются **только новые** посты с ключевым словом. Посты на момент первого запуска игнорируются.

## Что понадобится

- Windows Server 2019 или 2022 (или Windows 10/11)
- Python 3.10+ ([python.org](https://www.python.org/downloads/))
- Доступ по RDP для первого входа в VK (SMS-код)
- Аккаунт VK — администратор канала `https://vk.com/im/channels/-230930322`
- Ссылки на сообщества для парсинга

---

## 1. Установка Python

1. Скачайте Python с [python.org/downloads](https://www.python.org/downloads/)
2. При установке отметьте:
   - **Add python.exe to PATH**
   - **Install pip**
3. Завершите установку

Проверка в **PowerShell** (от администратора не обязательно):

```powershell
python --version
pip --version
```

Нужен Python **3.10** или выше.

---

## 2. Папка проекта

Скопируйте проект на сервер, например:

```
C:\vk-community-parser
```

```powershell
cd C:\vk-community-parser
```

---

## 3. Виртуальное окружение, зависимости и Chromium

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

Если PowerShell блокирует активацию venv:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Через **cmd**:

```cmd
cd C:\vk-community-parser
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 4. Настройка config.json

```powershell
copy config.example.json config.json
notepad config.json
```

Пример:

```json
{
  "keyword": "Мы теперь и в Мах",
  "source_community_urls": [
    "https://vk.com/clivpiter"
  ],
  "target_channel_url": "https://vk.com/im/channels/-230930322",
  "poll_interval_seconds": 300,
  "posts_per_check": 20,
  "playwright_headless": true,
  "playwright_slow_mo_ms": 50
}
```

| Параметр | Описание |
|----------|----------|
| `keyword` | Ключевое слово в тексте поста |
| `source_community_urls` | Ссылки на сообщества |
| `target_channel_url` | Канал для публикации |
| `poll_interval_seconds` | Интервал проверки (300 = 5 мин) |
| `posts_per_check` | Сколько последних постов смотреть |
| `playwright_headless` | `false` при первом входе, `true` для автозапуска |
| `playwright_slow_mo_ms` | Задержка между действиями в браузере (мс) |

---

## 5. Учётные данные VK (.env)

```powershell
copy .env.example .env
notepad .env
```

```env
VK_LOGIN=+79001234567
VK_PASSWORD=ваш_пароль
```

---

## 6. Первый вход в VK (обязательно вручную)

Подключитесь к серверу по **RDP** (нужен интерактивный сеанс для SMS).

В `config.json` на время входа установите:

```json
"playwright_headless": false
```

```powershell
cd C:\vk-community-parser
.\.venv\Scripts\Activate.ps1
python main.py --login-only
```

Скрипт:
1. Откроет Chromium
2. Введёт логин и пароль из `.env`
3. Попросит **код SMS** в консоли — введите и нажмите Enter
4. Сохранит сессию в `playwright_state.json`

Проверка и инициализация:

```powershell
python main.py --once
```

Перед автозапуском верните в `config.json`:

```json
"playwright_headless": true
```

---

## 7. Запуск вручную (мониторинг 24/7)

Пока открыто окно терминала:

```powershell
cd C:\vk-community-parser
.\.venv\Scripts\Activate.ps1
python main.py
```

Остановка: `Ctrl+C`

Одна проверка:

```powershell
python main.py --once
```

---

## 8. Автозапуск через Планировщик заданий

Для работы 24/7 без открытого RDP.

### 8.1. Файл start.bat

Создайте `C:\vk-community-parser\start.bat`:

```bat
@echo off
cd /d C:\vk-community-parser
call .venv\Scripts\activate.bat
python main.py
```

### 8.2. Задача в Планировщике

1. Откройте **Планировщик заданий** (`taskschd.msc`)
2. **Создать задачу...**
3. **Общие**:
   - Имя: `VK Parser`
   - Выполнять для: учётная запись, под которой выполнен `--login-only`
   - **Выполнять вне зависимости от регистрации пользователя** — можно включить для фоновой работы
4. **Триггеры** → **Создать**:
   - При запуске компьютера (или при входе в систему)
5. **Действия** → **Создать**:
   - Программа: `C:\vk-community-parser\start.bat`
   - Рабочая папка: `C:\vk-community-parser`
6. **Параметры**:
   - Перезапускать при сбое через **1 минуту**
   - Число попыток: **3**
7. Сохраните задачу (потребуется пароль учётной записи)

**Важно:** сессия VK (`playwright_state.json`) привязана к профилю пользователя. Задача должна выполняться под **тем же** пользователем, который делал `--login-only`.

---

## 9. Логи

```
C:\vk-community-parser\logs\vk-parser.log
```

Просмотр в PowerShell:

```powershell
Get-Content C:\vk-community-parser\logs\vk-parser.log -Wait
```

---

## 10. Полезные команды

| Действие | Команда |
|----------|---------|
| Первый вход / повторный вход | `python main.py --login-only` |
| Одна проверка | `python main.py --once` |
| Сбросить состояние | `python main.py --reinit --once` |
| Запуск без окна браузера | `python main.py --headless --once` |
| Активировать venv | `.\.venv\Scripts\Activate.ps1` |

Повторный вход (истекла сессия VK):

```powershell
python main.py --login-only
```

---

## 11. Обновление

```powershell
cd C:\vk-community-parser
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Перезапустите задачу в Планировщике или выполните `start.bat` заново.

---

## Как работает «только новые посты»

1. **Первый запуск** — видимые посты записываются в `state.json`, не копируются.
2. **Дальше** — копируются только новые посты с ключевым словом.
3. Посты без ключевого слова помечаются обработанными.

---

## Решение проблем

| Проблема | Решение |
|----------|---------|
| `python` не найден | Переустановите Python с **Add to PATH** |
| Ошибка активации venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: vk_api` | Используйте venv: `.\.venv\Scripts\python.exe main.py` |
| `Executable doesn't exist` | `python -m playwright install chromium` |
| Требуется SMS при каждом запуске | Повторите `--login-only` под тем же пользователем Windows |
| Задача в Планировщике не стартует | Проверьте пути в `start.bat`, рабочую папку, пароль учётной записи |
| Сессия VK не подхватывается | Задача должна работать от того же пользователя, что делал вход |
| `Не найдено поле ввода` | VK обновил вёрстку — нужна правка `playwright_bot.py` |
| Ошибка авторизации | Проверьте `VK_LOGIN` и `VK_PASSWORD` в `.env` |
| Посты не публикуются | Аккаунт должен быть админом канала |
| Скопировались старые посты | `python main.py --reinit --once` |

---

## Структура файлов

```
C:\vk-community-parser\
├── main.py
├── playwright_bot.py
├── config.json
├── .env
├── playwright_state.json   # сессия браузера VK
├── state.json              # обработанные посты
├── logs\vk-parser.log
├── start.bat               # для Планировщика заданий
└── .venv\
```
