import asyncio
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

# Токен бота берется из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Укажите ваш актуальный URL (ссылку на Railway или локальный ngrok-туннель)
WEB_APP_URL = ""

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    # Инлайн-кнопка для запуска WebApp прямо в сообщении
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить приложение",
                    web_app=WebAppInfo(url=WEB_APP_URL)
                )
            ]
        ]
    )
    
    text = "Приветствую на бета тесте"
    await message.answer(text, reply_markup=keyboard)

async def main():
    if not BOT_TOKEN:
        print("Ошибка: не задан BOT_TOKEN в переменных окружения!")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Подключаем роутер с командами
    dp.include_router(router)
    
    print("Telegram-бот запущен и ожидает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())