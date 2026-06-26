"""Работа с VK через Playwright: ручной вход, чтение стены, публикация в канал."""

from __future__ import annotations

import logging
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

VK_HOME_URL = "https://vk.com/feed"
VK_LOGIN_PAGE = "https://id.vk.com/auth"


@dataclass
class WallPost:
    post_id: str
    text: str
    photo_urls: list[str] = field(default_factory=list)
    community_url: str = ""


class VkPlaywrightBot:
    def __init__(
        self,
        *,
        storage_path: Path,
        headless: bool = False,
        slow_mo_ms: int = 50,
        fresh: bool = False,
    ) -> None:
        self.storage_path = storage_path
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self.fresh = fresh
        self._session_confirmed = False
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> VkPlaywrightBot:
        self.start(fresh=self.fresh)
        return self

    def __exit__(self, *_args: Any) -> None:
        self.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Браузер не запущен")
        return self._page

    def start(self, *, fresh: bool = False) -> None:
        if self._browser is not None:
            return

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
        )
        context_kwargs: dict[str, Any] = {
            "locale": "ru-RU",
            "viewport": {"width": 1366, "height": 900},
        }
        if not fresh and self.storage_path.exists():
            context_kwargs["storage_state"] = str(self.storage_path)

        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()
        logging.info("Браузер Playwright запущен")

    def stop(self) -> None:
        if self._context is not None:
            self.save_session()
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None
        logging.info("Браузер Playwright остановлен")

    def save_session(self) -> None:
        if self._context is None or not self._session_confirmed:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(self.storage_path))
        logging.info("Сессия браузера сохранена: %s", self.storage_path)

    def _has_auth_cookie(self) -> bool:
        if self._context is None:
            return False
        for cookie in self._context.cookies():
            if cookie.get("name") not in ("remixsid", "remixsid6"):
                continue
            if not cookie.get("value"):
                continue
            domain = cookie.get("domain", "")
            if "vk.com" in domain or "vk.ru" in domain:
                return True
        return False

    def is_logged_in(self) -> bool:
        page = self.page
        page.goto(VK_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(2)

        current_url = page.url.lower()
        if "id.vk.com" in current_url or "/login" in current_url:
            return False

        if not self._has_auth_cookie():
            return False

        login_link = page.locator(
            'a:has-text("Войти"), button:has-text("Войти"), '
            '[data-testid="enter-another-account"]'
        )
        if login_link.count() > 0 and login_link.first.is_visible():
            return False

        profile_selectors = [
            "#top_nav_link",
            '[data-testid="leftmenuitem"]',
            ".TopNavBtn--profile",
            '[data-testid="account-menu"]',
        ]
        for selector in profile_selectors:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                return True

        return False

    def wait_for_manual_login(self, *, force: bool = False) -> None:
        if not force and self.is_logged_in():
            logging.info("Сессия VK активна")
            self._session_confirmed = True
            return

        if self.headless:
            raise RuntimeError(
                "Сессия VK не найдена. Сначала выполните вход вручную:\n"
                "  python main.py --login-only\n"
                "(без --headless, в открытом браузере)"
            )

        page = self.page
        logging.info("Войдите в VK вручную в открытом браузере")
        page.goto(VK_LOGIN_PAGE, wait_until="domcontentloaded", timeout=60_000)

        print(
            "\n=== Вход в VK ===\n"
            "1. Войдите в аккаунт в браузере (логин, пароль, SMS).\n"
            "2. Откройте ленту https://vk.com/feed и убедитесь, что вы вошли.\n"
            "3. Вернитесь в консоль и нажмите Enter.\n"
        )
        input("Нажмите Enter после входа в VK... ")

        if not self.is_logged_in():
            raise RuntimeError(
                "Вход не подтверждён. Откройте vk.com/feed в браузере и войдите в аккаунт"
            )

        logging.info("Ручной вход подтверждён")
        self._session_confirmed = True
        self.save_session()

    def ensure_logged_in(self) -> None:
        if self.is_logged_in():
            logging.info("Сессия VK активна")
            self._session_confirmed = True
            return
        self.wait_for_manual_login()

    def _click_first(self, selectors: list[str]) -> bool:
        page = self.page
        for selector in selectors:
            button = page.locator(selector).first
            if button.count() == 0 or not button.is_visible():
                continue
            button.click()
            return True
        return False

    def _normalize_community_url(self, url: str) -> str:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url.lstrip('/')}"
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError(f"Некорректная ссылка на сообщество: {url}")
        return url

    def collect_wall_posts(self, community_url: str, *, limit: int) -> list[WallPost]:
        page = self.page
        url = self._normalize_community_url(community_url)
        logging.info("Открываю стену сообщества: %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(3)

        for _ in range(3):
            page.mouse.wheel(0, 2500)
            time.sleep(1)

        raw_posts: list[dict[str, Any]] = page.evaluate(
            """(limit) => {
                const result = [];
                const seen = new Set();
                const nodes = document.querySelectorAll('[data-post-id], div[id^="post-"]');

                for (const node of nodes) {
                    if (result.length >= limit) break;

                    const postId = node.getAttribute('data-post-id')
                        || (node.id || '').replace(/^post-/, '');
                    if (!postId || seen.has(postId)) continue;
                    seen.add(postId);

                    const textNode = node.querySelector(
                        '.wall_post_text, .vkitPost__text, [data-testid="post_text"], .post_text'
                    );
                    const text = textNode ? textNode.innerText.trim() : '';

                    const photoUrls = [];
                    const imgs = node.querySelectorAll(
                        'a.page_post_thumb_wrap img, .MediaGrid img, .vkitPhotoAlbumPhoto__image, img'
                    );
                    for (const img of imgs) {
                        const src = img.currentSrc || img.src || '';
                        if (!src || src.startsWith('data:')) continue;
                        if (!photoUrls.includes(src)) photoUrls.push(src);
                    }

                    result.push({ post_id: postId, text, photo_urls: photoUrls });
                }
                return result;
            }""",
            limit,
        )

        posts = [
            WallPost(
                post_id=str(item["post_id"]),
                text=str(item.get("text") or ""),
                photo_urls=[str(u) for u in item.get("photo_urls", []) if u],
                community_url=url,
            )
            for item in raw_posts
        ]
        logging.info("Найдено постов на стене: %s", len(posts))
        return posts

    def _download_photos(self, urls: list[str]) -> list[Path]:
        paths: list[Path] = []
        for index, url in enumerate(urls, start=1):
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            suffix = ".jpg"
            match = re.search(r"\.(jpe?g|png|webp)", urlparse(url).path, re.I)
            if match:
                suffix = f".{match.group(1).lower()}"
            temp = tempfile.NamedTemporaryFile(
                suffix=f"_{index}{suffix}",
                delete=False,
            )
            temp.write(response.content)
            temp.close()
            paths.append(Path(temp.name))
        return paths

    def publish_to_channel(
        self,
        channel_url: str,
        text: str,
        photo_urls: list[str] | None = None,
    ) -> None:
        page = self.page
        photo_urls = photo_urls or []
        temp_files: list[Path] = []

        try:
            logging.info("Публикую в канал: %s", channel_url)
            page.goto(channel_url, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(3)

            input_selectors = [
                '[data-testid="mail_text_input"] div[contenteditable="true"]',
                '.composer_richtext [contenteditable="true"]',
                '.im-chat-input--text [contenteditable="true"]',
                'div[contenteditable="true"]',
            ]
            typed = False
            for selector in input_selectors:
                field = page.locator(selector).first
                if field.count() == 0 or not field.is_visible():
                    continue
                field.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                if text:
                    page.keyboard.type(text, delay=20)
                typed = True
                break

            if not typed:
                raise RuntimeError("Не найдено поле ввода сообщения в канале")

            if photo_urls:
                temp_files = self._download_photos(photo_urls)
                attach_selectors = [
                    '[data-testid="attach_photo"]',
                    'button[aria-label*="фото" i]',
                    'button[aria-label*="photo" i]',
                    '.ComposerButton--attach',
                ]
                attached = False
                for selector in attach_selectors:
                    button = page.locator(selector).first
                    if button.count() == 0 or not button.is_visible():
                        continue
                    with page.expect_file_chooser(timeout=10_000) as chooser_info:
                        button.click()
                    chooser = chooser_info.value
                    chooser.set_files([str(path) for path in temp_files])
                    attached = True
                    time.sleep(2)
                    break

                if not attached:
                    file_input = page.locator('input[type="file"]').first
                    if file_input.count() > 0:
                        file_input.set_input_files([str(path) for path in temp_files])
                        attached = True
                        time.sleep(2)

                if not attached:
                    logging.warning("Не удалось прикрепить фото, отправляю только текст")

            sent = self._click_first([
                '[data-testid="send_button"]',
                'button[aria-label*="Отправить" i]',
                'button:has-text("Отправить")',
                '.im-send-btn',
            ])
            if not sent:
                page.keyboard.press("Enter")

            time.sleep(2)
            logging.info("Сообщение отправлено в канал")
        finally:
            for path in temp_files:
                path.unlink(missing_ok=True)
