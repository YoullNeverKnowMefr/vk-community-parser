# Установка VK Parser на Ubuntu 24.04

Инструкция для развёртывания на **Ubuntu 24.04 LTS** с автозапуском через **systemd** (работа 24/7).

Скрипт работает **полностью через Playwright** (браузер Chromium): вход в VK, чтение стены сообществ и публикация в канал — без API и без внешнего сервера токенов.

Копируются **только новые** посты с ключевым словом. Посты, которые уже есть на момент первого запуска, игнорируются.

## Что понадобится

- Сервер с Ubuntu 24.04 LTS
- Доступ по SSH с правами `sudo`
- Аккаунт VK — администратор канала `https://vk.com/im/channels/-230930322`
- Ссылки на сообщества для парсинга
- Телефон для SMS-кода при первом входе

---

## 1. Обновление системы и базовые пакеты

```bash
ssh user@IP_СЕРВЕРА
```

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip python3-full git nano curl
```

Проверка Python:

```bash
python3 --version
```

Нужен Python **3.10** или выше.

---

## 2. Пользователь для сервиса

```bash
sudo useradd --system --home-dir /opt/vk-community-parser --create-home --shell /usr/sbin/nologin vkparser
```

---

## 3. Копирование проекта

### Вариант А — `scp` с локального компьютера

На **локальной машине** (из папки проекта):

```bash
scp -r ./* user@IP_СЕРВЕРА:/tmp/vk-community-parser/
```

На **сервере**:

```bash
sudo mkdir -p /opt/vk-community-parser
sudo cp -r /tmp/vk-community-parser/* /opt/vk-community-parser/
sudo chown -R vkparser:vkparser /opt/vk-community-parser
```

### Вариант Б — `git`

```bash
sudo apt install -y git
sudo mkdir -p /opt/vk-community-parser
sudo git clone <URL_РЕПОЗИТОРИЯ> /opt/vk-community-parser
sudo chown -R vkparser:vkparser /opt/vk-community-parser
```

---

## 4. Python-окружение и Playwright

```bash
cd /opt/vk-community-parser
sudo -u vkparser python3 -m venv .venv
sudo -u vkparser .venv/bin/pip install --upgrade pip
sudo -u vkparser .venv/bin/pip install -r requirements.txt
```

Установка браузера Chromium:

```bash
sudo -u vkparser .venv/bin/playwright install chromium
```

Системные библиотеки для Chromium (от root):

```bash
sudo .venv/bin/playwright install-deps chromium
```

Если `venv` не создаётся:

```bash
sudo apt install -y python3-full
sudo -u vkparser python3 -m venv .venv
```

---

## 5. Настройка config.json

```bash
sudo -u vkparser cp config.example.json config.json
sudo -u vkparser nano config.json
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
| `posts_per_check` | Сколько последних постов смотреть за раз |
| `playwright_headless` | `true` для сервера без GUI (systemd) |
| `playwright_slow_mo_ms` | Задержка между действиями в браузере (мс) |

Для **первого входа** временно можно поставить `"playwright_headless": false` и запускать с `xvfb` (см. шаг 7). После сохранения сессии для systemd оставьте `"playwright_headless": true`.

---

## 6. Учётные данные VK (.env)

```bash
sudo -u vkparser cp .env.example .env
sudo -u vkparser nano .env
```

```env
VK_LOGIN=+79001234567
VK_PASSWORD=ваш_пароль
```

```bash
sudo chmod 600 /opt/vk-community-parser/.env
sudo chmod 600 /opt/vk-community-parser/config.json
```

---

## 7. Первый вход в VK (обязательно вручную)

Перед автозапуском нужно войти в VK и ввести **SMS-код**. Сессия сохранится в `playwright_state.json`.

### На сервере с графикой или через SSH с X11

```bash
sudo -u vkparser -i
cd /opt/vk-community-parser
source .venv/bin/activate
python main.py --login-only
```

### На сервере без дисплея (типичный VPS)

Установите виртуальный дисплей:

```bash
sudo apt install -y xvfb
```

Первый вход:

```bash
sudo -u vkparser -i
cd /opt/vk-community-parser
source .venv/bin/activate
xvfb-run python main.py --login-only
```

Скрипт:
1. Откроет Chromium
2. Введёт логин и пароль из `.env`
3. Попросит **код SMS** в консоли — введите и нажмите Enter
4. Сохранит сессию в `playwright_state.json`

После успешного входа:

```bash
exit
```

Проверка и инициализация (старые посты не копируются):

```bash
sudo -u vkparser .venv/bin/python main.py --once
```

Убедитесь, что в `config.json` стоит `"playwright_headless": true` перед запуском systemd.

---

## 8. Systemd-сервис

```bash
sudo cp /opt/vk-community-parser/deploy/vk-parser.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vk-parser
sudo systemctl start vk-parser
```

Проверка:

```bash
sudo systemctl status vk-parser
```

Ожидается: `Active: active (running)`.

---

## 9. Логи

```bash
sudo journalctl -u vk-parser -f
```

```bash
sudo tail -f /opt/vk-community-parser/logs/vk-parser.log
```

---

## 10. Управление сервисом

```bash
sudo systemctl start vk-parser
sudo systemctl stop vk-parser
sudo systemctl restart vk-parser
sudo systemctl status vk-parser
```

---

## 11. Полезные команды

Одна проверка:

```bash
cd /opt/vk-community-parser
sudo -u vkparser .venv/bin/python main.py --once
```

Сброс состояния (снова игнорировать текущие посты):

```bash
sudo -u vkparser .venv/bin/python main.py --reinit --once
sudo systemctl restart vk-parser
```

Повторный вход (истекла сессия VK):

```bash
sudo -u vkparser -i
cd /opt/vk-community-parser
source .venv/bin/activate
xvfb-run python main.py --login-only
```

Запуск без окна (явно):

```bash
sudo -u vkparser .venv/bin/python main.py --headless --once
```

---

## 12. Обновление

```bash
cd /opt/vk-community-parser
# git pull или scp новых файлов
sudo -u vkparser .venv/bin/pip install -r requirements.txt
sudo -u vkparser .venv/bin/playwright install chromium
sudo .venv/bin/playwright install-deps chromium
sudo systemctl restart vk-parser
```

---

## Как работает «только новые посты»

1. **Первый запуск** — видимые посты записываются в `state.json`, не копируются.
2. **Дальше** — копируются только новые посты с ключевым словом.
3. Посты без ключевого слова помечаются обработанными.

---

## Решение проблем

| Проблема | Решение |
|----------|---------|
| `externally-managed-environment` | Используйте venv (шаг 4) |
| `Browser closed` / ошибки Chromium | `sudo .venv/bin/playwright install-deps chromium` |
| `Executable doesn't exist` | `sudo -u vkparser .venv/bin/playwright install chromium` |
| Требуется SMS при каждом запуске | Повторите `python main.py --login-only`, проверьте `playwright_state.json` |
| `Не найдено поле ввода` / селекторы | VK обновил вёрстку — нужна правка `playwright_bot.py` |
| Ошибка авторизации | Проверьте `VK_LOGIN` и `VK_PASSWORD` в `.env` |
| Посты не публикуются | Аккаунт должен быть админом канала |
| Скопировались старые посты | `python main.py --reinit --once` |
| Нет прав на запись | `sudo chown -R vkparser:vkparser /opt/vk-community-parser` |
| На VPS нет дисплея | `xvfb-run` для `--login-only`, в config `playwright_headless: true` |

---

## Структура файлов

```
/opt/vk-community-parser/
├── main.py
├── playwright_bot.py
├── config.json
├── .env
├── playwright_state.json   # сессия браузера VK
├── state.json              # обработанные посты
├── logs/vk-parser.log
├── .venv/
└── deploy/vk-parser.service
```
