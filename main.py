import asyncio
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from config.settings import settings
from bot.bot_instance import create_bot_and_dispatcher

# Настройка красивого логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")


async def main():
    logger.info("==================================================")
    logger.info(" Запуск AI-бота строительного учета (Садик M-100) ")
    logger.info("==================================================")

    if settings.TELEGRAM_BOT_TOKEN == "MOCK_BOT_TOKEN":
        logger.warning(
            "ВНИМАНИЕ: TELEGRAM_BOT_TOKEN не задан в .env файле!\n"
            "Для подключения реального бота создайте бота в @BotFather и укажите токен в .env.\n"
            "Сейчас система готова к работе в тестовом/автономном режиме."
        )

    bot, dp = create_bot_and_dispatcher()

    logger.info(f"LLM Provider: {settings.LLM_PROVIDER} ({settings.LLM_MODEL})")
    logger.info(f"Google Sheets Configured: {bool(settings.GOOGLE_SPREADSHEET_ID)}")
    logger.info(f"Bitrix24 Configured: {bool(settings.BITRIX24_WEBHOOK_URL)}")

    try:
        logger.info("Запуск Telegram Polling...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка работы бота: {e}")
    finally:
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Принудительная остановка.")
