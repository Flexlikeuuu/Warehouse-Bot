import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_main_menu_keyboard
from config.settings import settings
from services.catalog_service import CatalogService
from services.sheets_service import GoogleSheetsService
from services.bitrix_service import Bitrix24Service

logger = logging.getLogger(__name__)
common_router = Router(name="common_router")


@common_router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "👋 *Приветствую, мастер!*\n\n"
        "Я AI-ассистент для учёта выполненных строительно-монтажных работ.\n\n"
        "🛠 *Что я умею:*\n"
        "1. 🗣 *Принимать отчёт текстом или голосом* в свободной форме.\n"
        "   _Пример:_ «Сегодня проложили медь 6-ку 15 м и 9-ку 15 м, изоляцию на них столько же, кабель 3х2,5 — 56 м, поставили 10 хомутов под фреон»\n"
        "2. 🔍 *Автоматически сопоставлять сметные позиции* и проверять единицы измерения.\n"
        "3. ⚠️ *Предупреждать о перерасходе*, если объем превышает остаток по смете.\n"
        "4. ❓ *Уточнять спорные позиции* (если не указан диаметр или сечение).\n"
        "5. ✍️ *Давать возможность всё проверить и исправить* перед записью.\n"
        "6. 📊 *Записывать данные в Google Таблицу* с автосозданием столбца с датой.\n"
        "7. 🏢 *Создавать задачу и публикацию в Битрикс24*.\n"
        "8. 💡 *Отвечать на вопросы по остаткам*, например: «_сколько осталось по кабелю 3х2,5?_»\n\n"
        "Просто отправьте мне голосовое сообщение или напишите текст!"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())


@common_router.message(Command("help"))
@common_router.message(F.text == "ℹ️ Справка / Команды")
async def handle_help(message: Message):
    help_text = (
        "📖 *Справка по работе с ботом:*\n\n"
        "• *Отправка отчета:* отправьте текстовое сообщение или голосовую заметку со списком выполненных работ.\n"
        "• *Вопрос по смете:* спросите «_сколько осталось по шпилькам?_» или «_какой остаток по кабелю 3х2,5?_».\n"
        "• /today — посмотреть и при необходимости исправить объемы, внесенные за сегодня.\n"
        "• /table — получить прямую ссылку на рабочую Google Таблицу.\n"
        "• /status — проверить статус подключения Google Sheets и Битрикс24.\n"
        "• /reload — перезагрузить справочник позиций из таблицы.\n"
        "• /cancel — сбросить текущее действие и вернуться в меню."
    )
    await message.answer(help_text, parse_mode="Markdown")


@common_router.message(Command("table"))
@common_router.message(F.text == "📊 Ссылка на таблицу")
async def handle_table_link(message: Message, sheets_service: GoogleSheetsService):
    url = sheets_service.get_sheet_link()
    kb = None
    if url and url.startswith("http"):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Открыть Google Таблицу", url=url)]
        ])
    await message.answer(
        f"📊 <b>Рабочая таблица объекта:</b>\n"
        f'<a href="{url}">{url}</a>\n\n'
        "Все внесенные ботом объемы автоматически попадают в столбец с текущей датой.",
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True
    )


@common_router.message(Command("status"))
async def handle_status(message: Message, sheets_service: GoogleSheetsService, bitrix_service: Bitrix24Service):
    if sheets_service.apps_script_url and sheets_service.apps_script_url.startswith("http"):
        g_conf = "✅ Подключен (Apps Script Webhook)"
    elif sheets_service.is_configured():
        g_conf = "✅ Настроена (Google Sheets API)"
    else:
        g_conf = "⚠️ Локальный режим (Excel fallback)"

    b_conf = "✅ Подключен" if bitrix_service.is_configured() else "⚠️ Режим симуляции (вебхук не задан)"

    b_status = "Не проверялось"
    if bitrix_service.is_configured():
        ok, msg = await bitrix_service.verify_connection()
        b_status = "🟢 Доступен" if ok else f"🔴 Ошибка ({msg})"

    current_model = settings.GEMINI_MODEL if settings.LLM_PROVIDER == "gemini" else settings.LLM_MODEL

    text = (
        "⚙️ *Статус интеграций системы:*\n\n"
        f"• *Google Sheets:* {g_conf}\n"
        f"  Таблица: `{sheets_service.spreadsheet_id or 'Локальный Excel'}`\n\n"
        f"• *Битрикс24 REST API:* {b_conf}\n"
        f"  Статус соединения: {b_status}\n\n"
        f"• *LLM Провайдер:* `{settings.LLM_PROVIDER}` (модель: `{current_model}`)\n"
        f"• *Голос (Whisper):* `{'Включен' if settings.OPENAI_API_KEY or settings.GROQ_API_KEY else 'Mock-режим'}`"
    )
    await message.answer(text, parse_mode="Markdown")


@common_router.message(Command("reload"))
async def handle_reload_catalog(message: Message, catalog_service: CatalogService, sheets_service: GoogleSheetsService):
    msg = await message.answer("🔄 Перезагрузка справочника позиций...")
    try:
        if sheets_service.is_configured():
            positions = sheets_service.load_positions_from_sheet()
            catalog_service.set_positions_from_raw_data(positions)
        else:
            catalog_service.load_from_excel()

        count = len(catalog_service.get_all())
        await msg.edit_text(f"✅ Справочник позиций успешно обновлен из таблицы! Загружено позиций: *{count}*.", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка обновления каталога: {e}")


@common_router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено. Вы в главном меню.", reply_markup=get_main_menu_keyboard())


@common_router.callback_query(F.data == "back_to_menu")
async def handle_back_menu_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Вы вернулись в главное меню.")

