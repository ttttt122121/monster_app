"""
Telegram-бот «Коллекционера вкусов» (aiogram 3.x). Работает отдельно от сайта (main.py).

Запуск:
    export BOT_TOKEN="123456:ABC..."                     # токен бота от @BotFather
    export WEB_APP_URL="https://your-app.up.railway.app" # адрес Mini App, только https
    python bot.py

Зависимости:  pip install aiogram
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEB_APP_URL = os.getenv("WEB_APP_URL", "").strip()

GREETING = "Приветствую на бета тесте"

log = logging.getLogger("bot")
router = Router()


def web_app_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопка запуска Mini App. Telegram принимает для web_app только https-адреса,
    поэтому без корректного WEB_APP_URL кнопки нет."""
    if not WEB_APP_URL.startswith("https://"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Запустить приложение", web_app=WebAppInfo(url=WEB_APP_URL)),
    ]])


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(GREETING, reply_markup=web_app_keyboard())


async def main() -> None:
    if not BOT_TOKEN:
        sys.exit("Ошибка: не задана переменная окружения BOT_TOKEN. "
                 "Получите токен у @BotFather и запустите: BOT_TOKEN=... python bot.py")
    if not WEB_APP_URL.startswith("https://"):
        log.warning("WEB_APP_URL не задан или не начинается с https:// — /start будет отвечать без кнопки")

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