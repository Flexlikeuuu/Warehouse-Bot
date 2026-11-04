import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config.settings import settings
from bot.handlers.common import common_router
from bot.handlers.questions import questions_router
from bot.handlers.edit import edit_router
from bot.handlers.report import report_router

from services.catalog_service import CatalogService
from services.sheets_service import GoogleSheetsService
from services.bitrix_service import Bitrix24Service
from services.llm_service import LLMService
from services.voice_service import VoiceService

logger = logging.getLogger(__name__)


def create_bot_and_dispatcher():
    """Инициализация Telegram бота и диспетчера со всеми сервисами."""
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Инициализация сервисов
    catalog_service = CatalogService(excel_path=settings.LOCAL_EXCEL_PATH)
    sheets_service = GoogleSheetsService()
    bitrix_service = Bitrix24Service()
    llm_service = LLMService()
    voice_service = VoiceService()

    # Загружаем позиции из Google Sheets (если настроены) или из Excel
    try:
        if sheets_service.is_configured():
            positions = sheets_service.load_positions_from_sheet()
            catalog_service.set_positions_from_raw_data(positions)
            logger.info("Справочник позиций успешно загружен из Google Sheets")
        else:
            catalog_service.load_from_excel()
            logger.info("Справочник позиций загружен из локального Excel")
    except Exception as e:
        logger.warning(f"Ошибка предварительной загрузки Google Sheets: {e}. Загрузка из Excel...")
        catalog_service.load_from_excel()

    # Передаем зависимости в workflow_data хэндлеров
    dp["catalog_service"] = catalog_service
    dp["sheets_service"] = sheets_service
    dp["bitrix_service"] = bitrix_service
    dp["llm_service"] = llm_service
    dp["voice_service"] = voice_service

    # Подключаем роутеры в правильном порядке
    dp.include_router(common_router)
    dp.include_router(questions_router)
    dp.include_router(edit_router)
    dp.include_router(report_router)

    return bot, dp

