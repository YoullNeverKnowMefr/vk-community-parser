# Установка и запуск VK Parser на Windows

Инструкция для **Windows 10/11**. Скрипт копирует **только новые** посты из сообществ VK в канал по ключевому слову.

## Что понадобится

- Windows 10 или 11
- Python 3.10+ ([python.org](https://www.python.org/downloads/))
- Аккаунт VK — администратор канала `https://vk.com/im/channels/-230930322`
- Ссылки на сообщества для парсинга

---

## 1. Установка Python

1. Скачайте Python с [python.org/downloads](https://www.python.org/downloads/)
2. При установке **обязательно** отметьте:
   - **Add python.exe to PATH**
   - **Install pip**
3. Завершите установку

Проверьте в **PowerShell** или **cmd**:

```powershell
python --version
pip --version
```

Должно показать Python 3.10 или выше.

---

## 2. Подготовка папки проекта

Скопируйте папку `vk-community-parser` в удобное место, например:

```
C:\vk-community-parser
```

Откройте PowerShell в этой папке:

```powershell
cd C:\vk-community-parser
```

---

## 3. Виртуальное окружение и зависимости

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Установка браузера для Playwright (нужно один раз):

```powershell
python -m playwright install chromium
```

Если PowerShell блокирует активацию venv:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Альтернатива через **cmd**:

```cmd
cd C:\vk-community-parser
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
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
    "https://vk.com/example_group1",
    "https://vk.com/club123456"
  ],
  "target_channel_url": "https://vk.com/im/channels/-230930322",
  "poll_interval_seconds": 300,
  "posts_per_check": 20
}
```

| Параметр | Описание |
|----------|----------|
| `source_community_urls` | Ссылки на сообщества для парсинга |
| `target_channel_url` | Канал, куда копировать посты |
| `poll_interval_seconds` | Интервал проверки (300 = 5 минут) |
| `posts_per_check` | Сколько последних постов проверять |

---

## 5. Учётные данные VK (опционально)

Можно хранить логин и пароль в файле `.env`:

```powershell
copy .env.example .env
notepad .env
```

```env
VK_LOGIN=79001234567
VK_PASSWORD=ваш_пароль
```

Если `.env` не создан — логин и пароль запросятся при запуске.

---

## 6. Первый вход в VK (access_token)

VK блокирует неофициальный вход через **VK ID**. Используйте **access_token** от своего приложения.

### Шаг 1 — создайте приложение

1. Откройте [dev.vk.com](https://dev.vk.com)
2. **Мои приложения** → **Создать** → тип **Standalone**
3. Скопируйте **ID приложения**

### Шаг 2 — получите токен

```powershell
cd C:\vk-community-parser
.\.venv\Scripts\Activate.ps1

# Рекомендуется: получить токен через Playwright (откроется Chromium, токен заберётся автоматически)
python main.py --login-only --playwright
```

Скрипт откроет Chrome с инструкцией и страницей авторизации VK.

1. Войдите в VK и разрешите доступ
2. В адресной строке найдите `access_token=vk1.a.XXXX...`
3. Скопируйте токен (до `&expires_in`)
4. Вставьте в терминал

Токен сохранится в `.env`.

Пример `.env`:

```env
VK_APP_ID=12345678
VK_ACCESS_TOKEN=vk1.a.ваш_токен
```

Без браузера: `python main.py --login-only --no-browser`

---

## 7. Первая инициализация

Пометить существующие посты как старые (не копировать их):

```powershell
python main.py --once
```

В логе должно появиться сообщение об инициализации и количестве проигнорированных постов.

---

## 8. Запуск в режиме мониторинга

Для постоянной работы (пока открыто окно терминала):

```powershell
cd C:\vk-community-parser
.\.venv\Scripts\Activate.ps1
python main.py
```

Скрипт будет проверять сообщества каждые 5 минут (или как задано в `config.json`).

Остановка: `Ctrl+C`

### Одна проверка без демона

```powershell
python main.py --once
```

---

## 9. Автозапуск при включении Windows (Планировщик заданий)

Чтобы скрипт работал 24/7 без открытого терминала:

### 9.1. Создайте bat-файл запуска

Создайте файл `C:\vk-community-parser\start.bat`:

```bat
@echo off
cd /d C:\vk-community-parser
call .venv\Scripts\activate.bat
python main.py
```

### 9.2. Добавьте задачу в Планировщик

1. Откройте **Планировщик заданий** (`taskschd.msc`)
2. **Создать задачу...**
3. Вкладка **Общие**:
   - Имя: `VK Parser`
   - Запуск с наивысшими правами: **снять**
   - Выполнять для всех пользователей / только для вашего — на выбор
4. Вкладка **Триггеры** → **Создать**:
   - Начать задачу: **При входе в систему** (или **При запуске компьютера**)
5. Вкладка **Действия** → **Создать**:
   - Действие: **Запуск программы**
   - Программа: `C:\vk-community-parser\start.bat`
   - Рабочая папка: `C:\vk-community-parser`
6. Вкладка **Параметры**:
   - При сбое перезапускать через: **1 минута**
   - Число попыток: **3**
7. Сохраните задачу

Проверка: перезагрузите ПК или запустите задачу вручную через Планировщик.

---

## 10. Просмотр логов

Логи пишутся в файл:

```
C:\vk-community-parser\logs\vk-parser.log
```

Открыть в PowerShell:

```powershell
Get-Content C:\vk-community-parser\logs\vk-parser.log -Wait
```

---

## 11. Полезные команды

| Действие | Команда |
|----------|---------|
| Войти в VK заново | `python main.py --login-only` |
| Одна проверка | `python main.py --once` |
| Сбросить состояние | `python main.py --reinit --once` |
| Активировать venv | `.\.venv\Scripts\Activate.ps1` |

---

## 12. Обновление скрипта

```powershell
cd C:\vk-community-parser
.\.venv\Scripts\Activate.ps1
# замените файлы проекта на новые версии
pip install -r requirements.txt
```

Если скрипт запущен через Планировщик — перезапустите задачу или перезагрузите ПК.

---

## Как работает «только новые посты»

1. При **первом запуске** все видимые посты записываются в `state.json` и не копируются.
2. Далее копируются только **новые** посты с ключевым словом «Мы теперь и в Мах».
3. Посты без ключевого слова тоже помечаются обработанными.

---

## Решение проблем

| Проблема | Решение |
|----------|---------|
| `python` не найден | Переустановите Python с галочкой **Add to PATH** |
| Ошибка активации venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Требуется SMS при каждом запуске | Запустите `python main.py --login-only`, выберите «Запомнить устройство» |
| Ошибка авторизации | Проверьте логин/пароль в `.env` |
| Посты не публикуются | Аккаунт должен быть админом канала |
| Скопировались старые посты | `python main.py --reinit --once` |
| Скрипт не стартует из Планировщика | Проверьте пути в `start.bat`, укажите рабочую папку |
| Нет файла логов | Запустите скрипт хотя бы раз — папка `logs` создаётся автоматически |

---

## Структура файлов

```
C:\vk-community-parser\
├── main.py
├── config.json
├── .env                  (опционально)
├── session.vk            (создаётся после входа)
├── state.json            (список обработанных постов)
├── logs\vk-parser.log
├── start.bat             (для автозапуска)
└── .venv\
```
