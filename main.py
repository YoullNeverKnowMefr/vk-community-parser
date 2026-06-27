#!/usr/bin/env python3
"""Парсинг постов из сообществ VK и публикация в канал через Playwright."""

from __future__ import annotations

import argparse
import json
import logging
import re
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 13)


def check_runtime() -> None:
    version = sys.version_info[:3]
    if version < MIN_PYTHON:
        print(
            f"Нужен Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+, "
            f"у вас {version[0]}.{version[1]}.{version[2]}"
        )
        sys.exit(1)
    if version > MAX_PYTHON:
        print(
            f"Python {version[0]}.{version[1]} не поддерживается "
            "(ошибка greenlet/playwright на Windows).\n"
            "Установите Python 3.12: https://www.python.org/downloads/\n"
            "Затем:\n"
            "  py -3.12 -m venv .venv\n"
            "  .venv\\Scripts\\activate\n"
            "  pip install -r requirements.txt\n"
            "  python -m playwright install chromium"
        )
        sys.exit(1)
    if ".venv" not in str(Path(sys.executable).resolve()).lower():
        print(
            "Предупреждение: запуск не из .venv. Рекомендуется:\n"
            "  python -m venv .venv\n"
            "  .venv\\Scripts\\activate\n"
            "  pip install -r requirements.txt"
        )


check_runtime()

from playwright_bot import VkPlaywrightBot, WallPost

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
BROWSER_STATE_PATH = BASE_DIR / "playwright_state.json"
LOG_PATH = BASE_DIR / "logs" / "vk-parser.log"
DEFAULT_TARGET_CHANNEL_URL = "https://vk.com/im/channels/-230930322"

_shutdown_requested = False


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        example = BASE_DIR / "config.example.json"
        if example.exists():
            CONFIG_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Создан {CONFIG_PATH}. Заполните настройки и запустите снова.")
            sys.exit(1)
        raise FileNotFoundError(f"Не найден {CONFIG_PATH}")
    return load_json(CONFIG_PATH, {})


def load_state() -> dict[str, Any]:
    raw = load_json(STATE_PATH, None)
    if raw is None:
        return {"initialized": False, "started_at": None, "processed": []}
    if isinstance(raw, list):
        return {"initialized": False, "started_at": None, "processed": raw}
    return {
        "initialized": bool(raw.get("initialized", False)),
        "started_at": raw.get("started_at"),
        "processed": list(raw.get("processed", [])),
    }


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_PATH, state)


def processed_set(state: dict[str, Any]) -> set[str]:
    return set(state.get("processed", []))


def setup_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def request_shutdown(signum: int, _frame: Any) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logging.info("Получен сигнал %s, завершение после текущей итерации...", signum)


def normalize_post_id(post_id: str) -> str:
    post_id = post_id.strip()
    if re.match(r"^-?\d+_\d+$", post_id):
        return post_id
    return post_id


def post_key(community_url: str, post: WallPost) -> str:
    return f"{community_url}::{normalize_post_id(post.post_id)}"


def post_contains_keyword(post: WallPost, keyword: str) -> bool:
    return keyword.lower() in post.text.lower()


def initialize_baseline(
    bot: VkPlaywrightBot,
    config: dict[str, Any],
    state: dict[str, Any],
) -> None:
    if state.get("initialized"):
        return

    posts_per_check = int(config.get("posts_per_check", 20))
    source_urls = config.get("source_community_urls", [])
    if not source_urls:
        raise ValueError("В config.json укажите source_community_urls")

    seen = processed_set(state)
    for community_url in source_urls:
        posts = bot.collect_wall_posts(community_url, limit=posts_per_check)
        for post in posts:
            seen.add(post_key(community_url, post))
        logging.info(
            "Инициализация %s: помечено %s постов как старые (только с момента запуска — новые)",
            community_url,
            len(posts),
        )

    state["processed"] = sorted(seen)
    state["initialized"] = True
    state["started_at"] = int(time.time())
    save_state(state)
    logging.info("Базовая инициализация завершена")


def process_community(
    bot: VkPlaywrightBot,
    community_url: str,
    target_channel_url: str,
    keyword: str,
    posts_per_check: int,
    state: dict[str, Any],
) -> int:
    copied = 0
    seen = processed_set(state)
    posts = bot.collect_wall_posts(community_url, limit=posts_per_check)
    new_posts = [p for p in posts if post_key(community_url, p) not in seen]
    logging.info("Новых постов на стене (не из baseline): %s", len(new_posts))

    for post in new_posts:
        key = post_key(community_url, post)
        if not post.text.strip():
            logging.warning(
                "Пост %s: текст не извлечён, оставляю для следующей проверки",
                post.post_id,
            )
            continue

        if not post_contains_keyword(post, keyword):
            logging.info(
                "Пост %s: нет ключевого слова «%s» (пропуск)",
                post.post_id,
                keyword,
            )
            seen.add(key)
            continue

        logging.info(
            "Новый пост %s с ключевым словом «%s»",
            post.post_id,
            keyword,
        )

        try:
            bot.publish_to_channel(
                target_channel_url,
                post.text,
                post.photo_urls,
                return_to_url=community_url,
            )
        except Exception as error:
            logging.error(
                "Ошибка публикации поста %s из %s: %s",
                post.post_id,
                community_url,
                error,
            )
            continue

        seen.add(key)
        state["processed"] = sorted(seen)
        save_state(state)
        copied += 1
        logging.info(
            "Скопирован пост %s из %s в канал",
            post.post_id,
            community_url,
        )

    state["processed"] = sorted(seen)
    return copied


def run_once(bot: VkPlaywrightBot, config: dict[str, Any], state: dict[str, Any]) -> int:
    keyword = config.get("keyword", "Мы теперь и в Мах")
    posts_per_check = int(config.get("posts_per_check", 20))
    source_urls = config.get("source_community_urls", [])
    target_channel_url = config.get("target_channel_url", DEFAULT_TARGET_CHANNEL_URL)

    if not source_urls:
        raise ValueError("В config.json укажите source_community_urls")

    initialize_baseline(bot, config, state)

    total = 0
    logging.info("Канал для публикации: %s", target_channel_url)
    for community_url in source_urls:
        logging.info("Проверка сообщества: %s", community_url)
        total += process_community(
            bot,
            community_url,
            target_channel_url,
            keyword,
            posts_per_check,
            state,
        )

    save_state(state)
    return total


def sleep_interruptible(seconds: int) -> None:
    end_at = time.time() + seconds
    while time.time() < end_at and not _shutdown_requested:
        time.sleep(min(1, end_at - time.time()))


def create_bot(config: dict[str, Any], *, fresh: bool = False) -> VkPlaywrightBot:
    return VkPlaywrightBot(
        storage_path=BROWSER_STATE_PATH,
        headless=bool(config.get("playwright_headless", False)),
        slow_mo_ms=int(config.get("playwright_slow_mo_ms", 50)),
        fresh=fresh,
    )


def run_daemon(
    config: dict[str, Any],
    state: dict[str, Any],
    poll_interval: int,
) -> None:
    with create_bot(config) as bot:
        bot.ensure_logged_in()
        while not _shutdown_requested:
            try:
                copied = run_once(bot, config, state)
                logging.info("Проверка завершена. Скопировано новых постов: %s", copied)
            except Exception:
                logging.exception("Ошибка во время проверки")

            if _shutdown_requested:
                break

            logging.info("Следующая проверка через %s сек.", poll_interval)
            sleep_interruptible(poll_interval)

    logging.info("Сервис остановлен")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Копирует новые посты из сообществ VK в канал через Playwright",
    )
    parser.add_argument("--once", action="store_true", help="Одна проверка и выход")
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="Открыть браузер, войти в VK вручную и сохранить сессию",
    )
    parser.add_argument(
        "--reinit",
        action="store_true",
        help="Сбросить state.json и заново пометить текущие посты как старые",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запуск браузера без окна",
    )
    args = parser.parse_args()

    setup_logging(LOG_PATH)
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    config = load_config() if CONFIG_PATH.exists() else {}
    if args.headless:
        config["playwright_headless"] = True

    state = load_state()
    if args.reinit and STATE_PATH.exists():
        STATE_PATH.unlink()
        state = load_state()
        logging.info("Состояние сброшено")

    if args.login_only:
        login_config = dict(config)
        login_config["playwright_headless"] = False
        with create_bot(login_config, fresh=True) as bot:
            bot.wait_for_manual_login(force=True)
        return

    poll_interval = int(config.get("poll_interval_seconds", 300))

    if args.once:
        with create_bot(config) as bot:
            bot.ensure_logged_in()
            copied = run_once(bot, config, state)
        logging.info("Готово. Скопировано новых постов: %s", copied)
        return

    logging.info("Запущен режим мониторинга 24/7. Интервал: %s сек.", poll_interval)
    run_daemon(config, state, poll_interval)


if __name__ == "__main__":
    main()
