import asyncio
import logging
import sys
import os

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from services.bitrix_service import Bitrix24Service
from models.schemas import ReportItem, CatalogPosition

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_bitrix")


async def main():
    logger.info("--- Проверка интеграции с Битрикс24 ---")
    b24 = Bitrix24Service()

    if not b24.is_configured():
        logger.error(
            "❌ Вебхук Битрикс24 не настроен!\n"
            "Пожалуйста, откройте файл .env и укажите параметр BITRIX24_WEBHOOK_URL.\n"
            "Пример: BITRIX24_WEBHOOK_URL=https://b24-xxxx.bitrix24.ru/rest/1/yyyy/"
        )
        return

    logger.info(f"Вебхук URL: {b24.webhook_url}")
    ok, msg = await b24.verify_connection()
    if not ok:
        logger.error(f"❌ Ошибка соединения: {msg}")
        return
    logger.info(f"✅ Соединение с Битрикс24 успешно: {msg}")

    # Создание тестовой задачи и публикации
    test_pos = CatalogPosition(
        row_idx=17,
        section="ОВ 3",
        item_num="13",
        name="Фреонопровод медный Д6,35",
        unit="м",
        plan_qty=265,
        price_per_unit=10,
        total_price=2650,
        completed_qty=140,
        remaining_qty=125
    )
    test_item = ReportItem(
        position=test_pos,
        volume=15.0,
        unit="м",
        raw_text="медь 6-ка 15 м"
    )

    logger.info("Отправка тестового дневного отчета в Битрикс24...")
    res = await b24.send_report(
        items=[test_item],
        master_name="Тестовый Инженер",
        sheet_url="https://docs.google.com/spreadsheets/d/example/edit"
    )

    logger.info(f"Результат: {res}")
    if res.get("success"):
        logger.info(f"🎉 Задача успешно создана! Ссылка: {res.get('task_url')}")
    else:
        logger.warning(f"Ошибки при отправке: {res.get('errors')}")


if __name__ == "__main__":
    asyncio.run(main())

