import datetime
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import ReportStates
from bot.keyboards import get_today_entries_keyboard, get_main_menu_keyboard
from services.catalog_service import CatalogService
from services.sheets_service import GoogleSheetsService
from models.schemas import ReportItem

logger = logging.getLogger(__name__)
edit_router = Router(name="edit_router")


@edit_router.message(Command("today"))
@edit_router.message(F.text == "📋 Данные за сегодня")
async def handle_show_today_entries(
    message: Message, 
    state: FSMContext,
    catalog_service: CatalogService,
    sheets_service: GoogleSheetsService
):
    """Показывает мастеру данные, уже внесенные в таблицу за сегодня."""
    await state.clear()
    today = datetime.date.today()
    entries = sheets_service.get_today_entries(today)

    if not entries:
        await message.answer(
            f"📋 *Данные за сегодня ({today.strftime('%d.%m.%Y')}):*\n\n"
            "За сегодня в таблице пока нет записей.\n"
            "Чтобы внести отчет, отправьте голосовое или текстовое сообщение с выполненными работами.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Сохраняем список записей в FSM для редактирования
    await state.update_data(today_entries=entries)

    lines = [f"📋 *Внесённые объёмы за сегодня ({today.strftime('%d.%m.%Y')}):*\n"]
    for idx, e in enumerate(entries, 1):
        pos = catalog_service.get_by_row(e["row_idx"])
        pos_name = pos.name if pos else f"Строка {e['row_idx']}"
        unit = pos.unit if pos else "ед."
        lines.append(f"*{idx}.* {pos_name}\n     • Зафиксировано: *{e['volume']} {unit}*")

    lines.append("\n_Если нужно исправить какую-то позицию, нажмите кнопку ниже:_")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_today_entries_keyboard(len(entries))
    )


@edit_router.callback_query(F.data.startswith("edit_today_"))
async def handle_select_today_entry_to_edit(
    call: CallbackQuery, 
    state: FSMContext,
    catalog_service: CatalogService
):
    idx = int(call.data.replace("edit_today_", ""))
    data = await state.get_data()
    entries = data.get("today_entries", [])

    if idx >= len(entries):
        await call.message.edit_text("Запись не найдена. Попробуйте снова.")
        return

    entry = entries[idx]
    pos = catalog_service.get_by_row(entry["row_idx"])
    pos_name = pos.name if pos else f"Строка {entry['row_idx']}"
    unit = pos.unit if pos else "ед."

    await state.update_data(selected_today_idx=idx, selected_today_row=entry["row_idx"])
    await state.set_state(ReportStates.editing_today_volume)

    await call.message.edit_text(
        f"✏️ *Корректировка записи за сегодня:*\n"
        f"Позиция: *{pos_name}*\n"
        f"Текущее значение: *{entry['volume']} {unit}*\n\n"
        f"Введите новое значение объёма (число, например 20):",
        parse_mode="Markdown"
    )


@edit_router.message(ReportStates.editing_today_volume)
async def handle_save_today_volume(
    message: Message, 
    state: FSMContext,
    catalog_service: CatalogService,
    sheets_service: GoogleSheetsService
):
    val_str = message.text.strip().replace(",", ".")
    try:
        new_vol = float(val_str)
        if new_vol < 0:
            await message.answer("Объем не может быть отрицательным. Введите число:")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите числовое значение (например: 15 или 0):")
        return

    data = await state.get_data()
    row_idx = data.get("selected_today_row")
    today = datetime.date.today()

    pos = catalog_service.get_by_row(row_idx)
    if not pos:
        await message.answer("Ошибка: позиция не найдена в каталоге.")
        await state.clear()
        return

    rep_item = ReportItem(
        position=pos,
        volume=new_vol,
        unit=pos.unit,
        raw_text="ручная правка за сегодня"
    )

    # Перезаписываем объем в Google Sheets / локальный Excel
    ok, msg = sheets_service.record_volumes([rep_item], today, overwrite=True)
    await state.clear()

    if ok:
        await message.answer(
            f"✅ *Данные за сегодня успешно обновлены!*\n\n"
            f"Позиция: *{pos.name}*\n"
            f"Новый объем за {today.strftime('%d.%m.%Y')}: *{new_vol} {pos.unit}*\n"
            f"📊 Таблица: {msg}",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(f"❌ Ошибка обновления: {msg}", reply_markup=get_main_menu_keyboard())

