"""
Telegram-бот «Коллекционера вкусов» (aiogram 3.x). Работает отдельно от сайта (main.py).

При первом /start бот просит выбрать язык (RU / UA / EN) и сохраняет выбор в той же базе SQLite,
что и приложение (таблица user_settings): тот же язык потом открывается в Mini App.
Если язык уже выбран, бот сразу присылает приветствие и кнопку запуска приложения.

Если пользователь блокирует/удаляет бота (my_chat_member: kicked / left), его запись в user_settings
удаляется: при следующем /start язык выбирается заново.

Настройки берутся из файла .env рядом с bot.py (см. .env.example) или из переменных окружения
(окружение приоритетнее файла):
    BOT_TOKEN=123456:ABC...                     # токен бота от @BotFather
    WEB_APP_URL= # адрес Mini App, только https
    DB_PATH=/data/app.db                        # необязательно: путь к базе сайта (по умолчанию как в main.py)
Запуск:  python bot.py

ВАЖНО: бот должен видеть тот же файл базы, что и main.py (один сервис/один том Railway, либо общий DB_PATH).

Зависимости:  pip install aiogram python-dotenv   (python-dotenv необязателен: без него .env читается встроенным разбором)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import KICKED, LEFT, ChatMemberUpdatedFilter, Command
from aiogram.types import (
    CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo,
)

BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    """Подгружает переменные из .env. Уже заданные в окружении не перезаписываются.
    Используется python-dotenv, а если он не установлен — встроенный разбор формата KEY=value."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False, encoding="utf-8")
        return
    except ImportError:
        pass
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")           # до чтения os.getenv ниже

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEB_APP_URL = os.getenv("WEB_APP_URL", "").strip()

# Путь к базе — тот же, что в main.py: DB_PATH из окружения, иначе app.db на томе /data (или рядом с файлом)
VOLUME_DIR = Path("/data") if Path("/data").is_dir() else BASE_DIR
DB_PATH = Path(os.getenv("DB_PATH", VOLUME_DIR / "app.db"))

LANGUAGES = ("ru", "ua", "en")

# Тексты бота на трёх языках
TEXTS = {
    "ru": {
        "greeting": "Приветствую на бета тесте",
        "button": "Запустить приложение",
        "saved": "Язык сохранён: Русский",
    },
    "ua": {
        "greeting": "Вітаю на бета-тесті",
        "button": "Запустити застосунок",
        "saved": "Мову збережено: Українська",
    },
    "en": {
        "greeting": "Welcome to the beta test",
        "button": "Launch the app",
        "saved": "Language saved: English",
    },
}
CHOOSE_LANGUAGE = "Choose language:"            # строго на английском: язык пользователя ещё неизвестен
LANGUAGE_BUTTONS = (("RU", "ru"), ("UA", "ua"), ("EN", "en"))
CALLBACK_PREFIX = "lang:"

log = logging.getLogger("bot")
router = Router()


# ───────────────────────── база данных ─────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_db() -> None:
    """Создаёт таблицу настроек, если бот запустился раньше сайта (схема та же, что в main.py)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS user_settings ("
            "user_id INTEGER PRIMARY KEY, "
            "language TEXT NOT NULL DEFAULT 'ru' CHECK (language IN ('ru', 'ua', 'en')))"
        )
        conn.commit()


def get_language(user_id: int) -> str | None:
    """Выбранный язык или None, если пользователь ещё не выбирал."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT language FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row and row[0] in LANGUAGES else None


def reset_language(user_id: int) -> None:
    """Удаляет настройки пользователя: язык выбирается заново при следующем /start."""
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        conn.commit()


def set_language(user_id: int, language: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, language) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET language = excluded.language",
            (user_id, language),
        )
        conn.commit()


# ───────────────────────── клавиатуры ─────────────────────────

def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data=CALLBACK_PREFIX + code) for label, code in LANGUAGE_BUTTONS
    ]])


def web_app_keyboard(language: str) -> InlineKeyboardMarkup | None:
    """Кнопка запуска Mini App. Telegram принимает для web_app только https-адреса,
    поэтому без корректного WEB_APP_URL кнопки нет."""
    if not WEB_APP_URL.startswith("https://"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=TEXTS[language]["button"], web_app=WebAppInfo(url=WEB_APP_URL)),
    ]])


# ───────────────────────── обработчики ─────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    language = await asyncio.to_thread(get_language, user_id)
    if language is None:                                  # первый запуск: сначала выбираем язык
        await message.answer(CHOOSE_LANGUAGE, reply_markup=language_keyboard())
        return
    await message.answer(TEXTS[language]["greeting"], reply_markup=web_app_keyboard(language))


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    """Сменить язык позже (выбор общий с приложением)."""
    await message.answer(CHOOSE_LANGUAGE, reply_markup=language_keyboard())


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED | LEFT))
async def on_bot_removed(event: ChatMemberUpdated) -> None:
    """Пользователь заблокировал или удалил бота: забываем его язык (в личном чате chat.id == user_id)."""
    if event.chat.type != "private":
        return
    await asyncio.to_thread(reset_language, event.chat.id)
    log.info("Бот удалён пользователем %s: язык сброшен", event.chat.id)


@router.callback_query(F.data.startswith(CALLBACK_PREFIX))
async def on_language_chosen(callback: CallbackQuery) -> None:
    language = (callback.data or "")[len(CALLBACK_PREFIX):]
    if language not in LANGUAGES:
        await callback.answer()
        return
    await asyncio.to_thread(set_language, callback.from_user.id, language)
    texts = TEXTS[language]
    await callback.answer(texts["saved"])
    # подтверждаем выбор и сразу даём кнопку запуска приложения
    text = f"{texts['saved']}\n\n{texts['greeting']}"
    try:
        await callback.message.edit_text(text, reply_markup=web_app_keyboard(language))
    except Exception:                                     # сообщение не удалось отредактировать — просто отправим новое
        await callback.message.answer(text, reply_markup=web_app_keyboard(language))


async def main() -> None:
    if not BOT_TOKEN:
        sys.exit("Ошибка: не задана переменная окружения BOT_TOKEN. "
                 "Получите токен у @BotFather и запустите: BOT_TOKEN=... python bot.py")
    if not WEB_APP_URL.startswith("https://"):
        log.warning("WEB_APP_URL не задан или не начинается с https:// — бот будет отвечать без кнопки запуска")

    init_db()
    log.info("База данных: %s", DB_PATH)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await bot.delete_webhook()           # если когда-то был вебхук, polling иначе не получит обновления
        log.info("Бот запущен")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass