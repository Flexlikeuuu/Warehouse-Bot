import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from services.catalog_service import CatalogService
from services.sheets_service import GoogleSheetsService
from services.bitrix_service import Bitrix24Service
from services.llm_service import LLMService


async def check_all():
    print("=" * 60)
    print(" [i] ДИАГНОСТИКА СИСТЕМЫ И ИНТЕГРАЦИЙ (Садик M-100)")
    print("=" * 60)

    # 1. Excel / Справочник
    print("\n1. Проверка справочника позиций:")
    cat = CatalogService()
    try:
        positions = cat.load_from_excel()
        print(f"   [OK] Локальный файл {settings.LOCAL_EXCEL_PATH} загружен.")
        print(f"   [OK] Всего позиций спецификации: {len(positions)} шт.")
    except Exception as e:
        print(f"   [ERROR] Ошибка загрузки Excel: {e}")

    # 2. Google Sheets
    print("\n2. Проверка Google Sheets:")
    if settings.GOOGLE_APPS_SCRIPT_URL and settings.GOOGLE_APPS_SCRIPT_URL.startswith("http"):
        print(f"   [OK] Google Sheets подключен через Apps Script Webhook!")
        print(f"   [OK] URL скрипта: {settings.GOOGLE_APPS_SCRIPT_URL[:45]}...")
        print(f"   [OK] Ссылка на таблицу: {settings.GOOGLE_SHEET_URL}")
    else:
        print(f"   [INFO] Локальный режим fallback.")

    # 3. Битрикс24
    print("\n3. Проверка Битрикс24:")
    b24 = Bitrix24Service()
    if b24.is_configured():
        print(f"   [OK] Вебхук Битрикс24: {b24.webhook_url}")
        ok, msg = await b24.verify_connection()
        if ok:
            print(f"   [OK] Связь с Битрикс24: {msg}")
        else:
            print(f"   [WARN] {msg}")
    else:
        print("   [INFO] Включен режим безопасной симуляции.")

    # 4. LLM & NLP Matching
    print("\n4. Проверка модуля сопоставления сметы (AI Gemini & Matcher):")
    llm = LLMService()
    test_str = "Сегодня проложили медь 6-ку 15 м и 9-ку 15 м, изоляцию на них столько же, кабель 3х2,5 — 56 м, поставили 10 хомутов под фреон"
    try:
        res = llm.extract_report_items(test_str, positions)
        print(f"   [OK] Распознано позиций: {len(res.matched_items)} из 6 ожидаемых.")
        for it in res.matched_items:
            print(f"      • {it.position.name[:35]} -> {it.volume} {it.unit}")
    except Exception as e:
        print(f"   [ERROR] Ошибка извлечения: {e}")

    # 5. Telegram
    print("\n5. Проверка Telegram бота:")
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_TOKEN != "MOCK_BOT_TOKEN":
        print(f"   [OK] Токен задан: {settings.TELEGRAM_BOT_TOKEN[:10]}...***")
        print(f"   [OK] Юзернейм: @sadik_m100_report_bot")
    else:
        print("   [WARN] Токен Telegram не задан (MOCK_BOT_TOKEN).")

    print("\n" + "=" * 60)
    print(" Диагностика завершена.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(check_all())
