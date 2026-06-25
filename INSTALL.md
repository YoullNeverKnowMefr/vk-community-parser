# Установка VK Parser на Debian 24.04

Инструкция для развёртывания скрипта на сервере **Debian 24.04** с автозапуском через **systemd** (работа 24/7).

Скрипт копирует **только новые** посты. Все посты, которые уже есть в сообществах на момент первого запуска, игнорируются.

## Что понадобится

- Сервер с Debian 24.04
- Доступ по SSH с правами `sudo`
- Аккаунт VK — администратор канала `https://vk.com/im/channels/-230930322`
- Ссылки на сообщества для парсинга

---

## 1. Обновление системы и установка пакетов

Подключитесь к серверу по SSH и выполните:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nano curl
```

Проверьте версию Python (нужна 3.10+):

```bash
python3 --version
```

---

## 2. Создание пользователя для сервиса

Отдельный системный пользователь изолирует процесс от root:

```bash
sudo useradd --system --home-dir /opt/vk-community-parser --create-home --shell /usr/sbin/nologin vkparser
```

---

## 3. Копирование проекта на сервер

### Вариант А — через `scp` с вашего компьютера

На **локальной машине** (из папки с проектом):

```bash
scp -r ./* user@IP_СЕРВЕРА:/tmp/vk-community-parser/
```

На **сервере**:

```bash
sudo mkdir -p /opt/vk-community-parser
sudo cp -r /tmp/vk-community-parser/* /opt/vk-community-parser/
sudo chown -R vkparser:vkparser /opt/vk-community-parser
```

### Вариант Б — через `git`

```bash
sudo mkdir -p /opt/vk-community-parser
sudo git clone <URL_РЕПОЗИТОРИЯ> /opt/vk-community-parser
sudo chown -R vkparser:vkparser /opt/vk-community-parser
```

---

## 4. Установка зависимостей Python

```bash
cd /opt/vk-community-parser
sudo -u vkparser python3 -m venv .venv
sudo -u vkparser .venv/bin/pip install --upgrade pip
sudo -u vkparser .venv/bin/pip install -r requirements.txt
```

---

## 5. Настройка config.json

```bash
sudo -u vkparser cp config.example.json config.json
sudo -u vkparser nano config.json
```

Пример содержимого:

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
| `source_community_urls` | Ссылки на сообщества, откуда парсить |
| `target_channel_url` | Канал, куда копировать посты |
| `poll_interval_seconds` | Интервал проверки в секундах (300 = 5 минут) |
| `posts_per_check` | Сколько последних постов проверять за раз |

---

## 6. Настройка учётных данных VK

```bash
sudo -u vkparser cp .env.example .env
sudo -u vkparser nano .env
```

Содержимое `.env`:

```env
VK_LOGIN=79001234567
VK_PASSWORD=ваш_пароль
```

Защитите конфиденциальные файлы:

```bash
sudo chmod 600 /opt/vk-community-parser/.env
sudo chmod 600 /opt/vk-community-parser/config.json
```

---

## 7. Первый вход в VK (обязательно вручную)

Перед автозапуском нужно один раз войти в VK и ввести **SMS-код** или код 2FA.

Временно переключитесь на пользователя `vkparser`:

```bash
sudo -u vkparser -i
cd /opt/vk-community-parser
source .venv/bin/activate
python main.py --login-only
```

Скрипт запросит:
1. Логин и пароль (если не заданы в `.env`)
2. **Код из SMS** или push-уведомления VK
3. При необходимости — цифры номера телефона для проверки безопасности
4. «Запомнить устройство» — выберите `y`

После успешного входа сессия сохранится в `session.vk`. Выйдите:

```bash
exit
```

Затем выполните первую инициализацию (пометить старые посты):

```bash
sudo -u vkparser .venv/bin/python main.py --once
```

---

## 8. Установка systemd-сервиса

```bash
sudo cp /opt/vk-community-parser/deploy/vk-parser.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vk-parser
sudo systemctl start vk-parser
```

Проверьте, что сервис запущен:

```bash
sudo systemctl status vk-parser
```

Должно быть: `Active: active (running)`.

---

## 9. Просмотр логов

Логи systemd:

```bash
sudo journalctl -u vk-parser -f
```

Логи в файле:

```bash
sudo tail -f /opt/vk-community-parser/logs/vk-parser.log
```

---

## 10. Управление сервисом

```bash
# Запуск
sudo systemctl start vk-parser

# Остановка
sudo systemctl stop vk-parser

# Перезапуск
sudo systemctl restart vk-parser

# Статус
sudo systemctl status vk-parser

# Автозапуск при загрузке сервера (уже включён на шаге 8)
sudo systemctl enable vk-parser
```

---

## 11. Полезные команды

```bash
cd /opt/vk-community-parser
sudo -u vkparser .venv/bin/python main.py --once
```

Сбросить состояние и снова игнорировать текущие посты как старые:

```bash
sudo -u vkparser .venv/bin/python main.py --reinit --once
sudo systemctl restart vk-parser
```

---

## 12. Обновление скрипта

```bash
cd /opt/vk-community-parser
# скопируйте новые файлы или выполните git pull
sudo -u vkparser .venv/bin/pip install -r requirements.txt
sudo systemctl restart vk-parser
```

---

## Как работает «только новые посты»

1. **Первый запуск** — все видимые посты записываются в `state.json` и не копируются.
2. **Дальше** — копируются только новые посты с ключевым словом «Мы теперь и в Мах».
3. Посты без ключевого слова тоже помечаются обработанными, чтобы не проверять их снова.

---

## Решение проблем

| Проблема | Решение |
|----------|---------|
| `python3-venv` не создаёт окружение | `sudo apt install -y python3-full` |
| Сервис падает сразу после старта | `sudo journalctl -u vk-parser -n 50` — смотрите ошибку |
| Требуется SMS/2FA при каждом перезапуске | Запустите `python main.py --login-only`, введите код и выберите «Запомнить устройство» |
| Ошибка авторизации | Проверьте `VK_LOGIN` и `VK_PASSWORD` в `.env` |
| Посты не публикуются | Аккаунт должен быть админом канала с правом публикации |
| Скопировались старые посты | `python main.py --reinit --once` и перезапуск сервиса |
| Нет прав на запись в `/opt` | `sudo chown -R vkparser:vkparser /opt/vk-community-parser` |

---

## Структура файлов после установки

```
/opt/vk-community-parser/
├── main.py              # основной скрипт
├── config.json          # настройки сообществ и канала
├── .env                 # логин и пароль VK
├── session.vk           # сохранённая сессия (создаётся автоматически)
├── state.json           # список обработанных постов
├── logs/vk-parser.log   # лог работы
├── .venv/               # виртуальное окружение Python
└── deploy/vk-parser.service
```
