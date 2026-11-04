import datetime
import logging
from typing import List, Dict, Any
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states import ReportStates
from bot.keyboards import (
    get_confirmation_keyboard, get_clarification_keyboard,
    get_item_select_keyboard, get_post_save_keyboard, get_main_menu_keyboard
)
from models.schemas import ReportItem, AmbiguousItem, CatalogPosition
from services.catalog_service import CatalogService
from services.llm_service import LLMService
from services.voice_service import VoiceService
from services.sheets_service import GoogleSheetsService
from services.bitrix_service import Bitrix24Service
from bot.handlers.questions import format_position_balance

logger = logging.getLogger(__name__)
report_router = Router(name="report_router")


def format_report_preview(items: List[ReportItem], target_date: datetime.date) -> str:
    """Форматирует красивый предпросмотр отчета перед записью."""
    date_str = target_date.strftime("%d.%m.%Y")
    lines = [f"📋 *Проверьте распознанный отчёт за {date_str}:*\n"]

    total_money = 0.0
    warnings = []

    for idx, it in enumerate(items, 1):
        pos = it.position
        cost = it.volume * pos.price_per_unit
        total_money += cost

        warn_badge = " ⚠️ *(превышение сметы)*" if it.is_over_limit else ""
        lines.append(
            f"*{idx}. {pos.name[:45]}*\n"
            f"   • Раздел: _{pos.section}_ | Смета #{pos.item_num or pos.row_idx}\n"
            f"   • Объем: *{it.volume} {it.unit}*{warn_badge}\n"
            f"   • Начислено: *{cost:.2f} руб.* (расценка: {pos.price_per_unit} руб./{it.unit})"
        )
        if it.warning_msg:
            warnings.append(f"• #{idx}: {it.warning_msg}")

    lines.append(f"\n💰 *Итого ЗП за день:* *{total_money:.2f} руб.*")

    if warnings:
        lines.append("\n⚠️ *Предупреждения по смете:*")
        lines.extend(warnings)

    lines.append("\n_Выберите действие ниже:_")
    return "\n".join(lines)


# =============================================================================
# Приём отчета: текст или голос
# =============================================================================

@report_router.message(F.voice | F.audio)
async def handle_voice_report(
    message: Message, 
    bot: Bot, 
    state: FSMContext,
    catalog_service: CatalogService,
    llm_service: LLMService,
    voice_service: VoiceService
):
    """Обработка голосового сообщения мастера."""
    status_msg = await message.answer("🎙 *Слушаю и распознаю голосовое сообщение...*", parse_mode="Markdown")

    file_id = message.voice.file_id if message.voice else message.audio.file_id
    try:
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        audio_data = file_bytes.read()

        transcribed_text = await voice_service.transcribe_audio_bytes(audio_data)
        await status_msg.edit_text(f"🎙 *Распознано:* «_{transcribed_text}_»", parse_mode="Markdown")

        # Передаем текст в единый процессинг
        await process_report_text(transcribed_text, message, state, catalog_service, llm_service)
    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}")
        await status_msg.edit_text(f"❌ Ошибка распознавания речи: {e}\nПожалуйста, отправьте отчёт текстом.")


@report_router.message(F.text, ~F.text.startswith("/"))
async def handle_text_report(
    message: Message, 
    state: FSMContext,
    catalog_service: CatalogService,
    llm_service: LLMService
):
    """Обработка текстового сообщения в свободной форме."""
    current_state = await state.get_state()
    # Если бот уже ждет специальный ввод (редактирование, добавление) — пропускаем к другим хэндлерам
    if current_state in [
        ReportStates.editing_volume, 
        ReportStates.adding_item_select, 
        ReportStates.adding_item_volume,
        ReportStates.editing_today_volume
    ]:
        return

    text = message.text.strip()
    if text in ["📝 Новый отчёт", "📋 Данные за сегодня", "📊 Ссылка на таблицу", "ℹ️ Справка / Команды"]:
        return

    await process_report_text(text, message, state, catalog_service, llm_service)


async def process_report_text(
    text: str, 
    message: Message, 
    state: FSMContext,
    catalog_service: CatalogService,
    llm_service: LLMService
):
    """Единая точка разбора текста отчета через LLM / матчер."""
    positions = catalog_service.get_all()
    extraction = llm_service.extract_report_items(text, positions)

    # 1. Если это вопрос по остаткам
    if extraction.is_question:
        if extraction.target_row_idx:
            pos = catalog_service.get_by_row(extraction.target_row_idx)
            if pos:
                await message.answer(format_position_balance(pos), parse_mode="Markdown")
                return
        await message.answer("🔍 Уточните, по какой именно позиции вы хотите узнать остаток.")
        return

    # 2. Если есть неоднозначные позиции (нужно уточнение мастера)
    if extraction.ambiguous_items:
        # Сохраняем уже распознанные позиции и очередь неоднозначностей
        ambig_serialized = [a.model_dump() for a in extraction.ambiguous_items]
        matched_serialized = [m.model_dump() for m in extraction.matched_items]

        await state.update_data(
            matched_items=matched_serialized,
            ambiguous_queue=ambig_serialized,
            current_ambiguous_idx=0,
            report_date=datetime.date.today().isoformat()
        )
        await state.set_state(ReportStates.clarifying_ambiguous)

        # Задаем первый вопрос на уточнение
        first_ambig = extraction.ambiguous_items[0]
        await message.answer(
            f"❓ *Требуется уточнение по позиции «{first_ambig.raw_text}»:*\n"
            f"{first_ambig.reason}\n\n"
            f"Выберите нужный вариант из спецификации:",
            parse_mode="Markdown",
            reply_markup=get_clarification_keyboard(first_ambig.candidates)
        )
        return

    # 3. Если ничего не распознано
    if not extraction.matched_items:
        await message.answer(
            "⚠️ Не удалось сопоставить работы с позициями спецификации.\n\n"
            "Попробуйте сформулировать иначе или используйте пример:\n"
            "_«Проложили медь 6-ку 15 м, кабель 3х2,5 — 56 м, хомуты под фреон 10 шт»_",
            parse_mode="Markdown"
        )
        return

    # 4. Все позиции однозначны — показываем экран подтверждения
    today = datetime.date.today()
    matched_serialized = [m.model_dump() for m in extraction.matched_items]
    await state.update_data(
        matched_items=matched_serialized,
        report_date=today.isoformat()
    )
    await state.set_state(ReportStates.confirming_report)

    text_preview = format_report_preview(extraction.matched_items, today)
    await message.answer(
        text_preview, 
        parse_mode="Markdown", 
        reply_markup=get_confirmation_keyboard(has_items=True)
    )


# =============================================================================
# Уточнение неоднозначностей (Inline кнопки)
# =============================================================================

@report_router.callback_query(ReportStates.clarifying_ambiguous, F.data.startswith("clarify_pick_"))
async def handle_clarify_pick(
    call: CallbackQuery, 
    state: FSMContext,
    catalog_service: CatalogService
):
    row_idx = int(call.data.replace("clarify_pick_", ""))
    data = await state.get_data()
    ambig_queue = data.get("ambiguous_queue", [])
    current_idx = data.get("current_ambiguous_idx", 0)
    matched_list = data.get("matched_items", [])

    current_item = ambig_queue[current_idx]
    pos = catalog_service.get_by_row(row_idx)

    if pos:
        vol = float(current_item.get("volume", 1.0))
        is_over = vol > pos.remaining_qty if pos.remaining_qty > 0 else False
        over_amt = max(0.0, vol - pos.remaining_qty) if is_over else 0.0
        warn_msg = f"Превышение сметы на {over_amt} {pos.unit}" if is_over else None

        new_rep_item = ReportItem(
            position=pos,
            volume=vol,
            unit=current_item.get("unit") or pos.unit,
            raw_text=current_item.get("raw_text", ""),
            is_over_limit=is_over,
            over_limit_amount=over_amt,
            warning_msg=warn_msg
        )
        matched_list.append(new_rep_item.model_dump())

    # Переходим к следующей неоднозначности в очереди
    next_idx = current_idx + 1
    if next_idx < len(ambig_queue):
        await state.update_data(matched_items=matched_list, current_ambiguous_idx=next_idx)
        next_ambig = ambig_queue[next_idx]
        from models.schemas import AmbiguousCandidate
        cands = [AmbiguousCandidate(**c) for c in next_ambig.get("candidates", [])]
        await call.message.edit_text(
            f"❓ *Уточнение по позиции «{next_ambig.get('raw_text')}»:*\n"
            f"{next_ambig.get('reason')}\n\n"
            f"Выберите подходящий вариант:",
            parse_mode="Markdown",
            reply_markup=get_clarification_keyboard(cands)
        )
    else:
        # Все неоднозначности разрешены — переходим к экрану подтверждения
        await state.update_data(matched_items=matched_list)
        await state.set_state(ReportStates.confirming_report)
        items_objs = [ReportItem(**it) for it in matched_list]
        today = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))
        text_preview = format_report_preview(items_objs, today)
        await call.message.edit_text(
            text_preview, 
            parse_mode="Markdown", 
            reply_markup=get_confirmation_keyboard(has_items=bool(items_objs))
        )


@report_router.callback_query(ReportStates.clarifying_ambiguous, F.data == "clarify_skip")
async def handle_clarify_skip(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ambig_queue = data.get("ambiguous_queue", [])
    current_idx = data.get("current_ambiguous_idx", 0)
    matched_list = data.get("matched_items", [])

    next_idx = current_idx + 1
    if next_idx < len(ambig_queue):
        await state.update_data(current_ambiguous_idx=next_idx)
        next_ambig = ambig_queue[next_idx]
        from models.schemas import AmbiguousCandidate
        cands = [AmbiguousCandidate(**c) for c in next_ambig.get("candidates", [])]
        await call.message.edit_text(
            f"❓ *Уточнение по позиции «{next_ambig.get('raw_text')}»:*\n"
            f"{next_ambig.get('reason')}\n\n"
            f"Выберите подходящий вариант:",
            parse_mode="Markdown",
            reply_markup=get_clarification_keyboard(cands)
        )
    else:
        await state.set_state(ReportStates.confirming_report)
        items_objs = [ReportItem(**it) for it in matched_list]
        today = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))
        text_preview = format_report_preview(items_objs, today)
        await call.message.edit_text(
            text_preview, 
            parse_mode="Markdown", 
            reply_markup=get_confirmation_keyboard(has_items=bool(items_objs))
        )


# =============================================================================
# Запись и подтверждение отчета
# =============================================================================

@report_router.callback_query(ReportStates.confirming_report, F.data == "confirm_save")
async def handle_confirm_save(
    call: CallbackQuery, 
    state: FSMContext,
    catalog_service: CatalogService,
    sheets_service: GoogleSheetsService,
    bitrix_service: Bitrix24Service
):
    data = await state.get_data()
    matched_list = data.get("matched_items", [])
    if not matched_list:
        await call.message.edit_text("Список работ пуст. Нечего сохранять.")
        await state.clear()
        return

    items = [ReportItem(**it) for it in matched_list]
    date_target = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))

    await call.message.edit_text("⏳ *Сохранение данных в Google Sheets и Битрикс24...*", parse_mode="Markdown")

    # 1. Запись в Google Sheets
    sheet_ok, sheet_msg = sheets_service.record_volumes(items, date_target)

    # 2. Обновление локальных остатков в каталоге
    for it in items:
        catalog_service.update_completed_qty(it.position.row_idx, it.volume)

    # 3. Отправка в Битрикс24 (Задача + Живая лента)
    user_name = call.from_user.full_name or call.from_user.username or "Мастер объекта"
    sheet_link = sheets_service.get_sheet_link()
    b24_res = await bitrix_service.send_report(
        items=items,
        date_target=date_target,
        master_name=user_name,
        sheet_url=sheet_link
    )

    await state.clear()

    # Формируем итоговое сообщение
    b24_status = "Задача и пост созданы" if b24_res.get("success") else "Режим симуляции / Ошибка"
    task_url = b24_res.get("task_url")

    resp_text = (
        f"✅ *Отчёт за {date_target.strftime('%d.%m.%Y')} успешно зафиксирован!*\n\n"
        f"📊 *Google Таблица:* {sheet_msg}\n"
        f"🏢 *Битрикс24:* {b24_status}\n\n"
        f"Записано позиций: *{len(items)}*.\n"
        f"Итоговая ЗП начислена: *{sum(it.volume * it.position.price_per_unit for it in items):.2f} руб.*"
    )

    await call.message.edit_text(
        resp_text, 
        parse_mode="Markdown", 
        reply_markup=get_post_save_keyboard(sheet_url=sheet_link, task_url=task_url)
    )


@report_router.callback_query(ReportStates.confirming_report, F.data == "btn_cancel_report")
async def handle_cancel_report(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Запись отчёта отменена. Данные не были сохранены.")


# =============================================================================
# Редактирование, добавление и удаление позиций перед записью
# =============================================================================

@report_router.callback_query(ReportStates.confirming_report, F.data == "btn_edit_volume")
async def handle_start_edit_volume(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = [ReportItem(**it) for it in data.get("matched_items", [])]
    await call.message.edit_text(
        "✏️ *Выберите позицию, объём которой хотите изменить:*",
        parse_mode="Markdown",
        reply_markup=get_item_select_keyboard(items, action_prefix="select_edit")
    )


@report_router.callback_query(ReportStates.confirming_report, F.data.startswith("select_edit_"))
async def handle_select_edit_item(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.replace("select_edit_", ""))
    await state.update_data(editing_item_idx=idx)
    await state.set_state(ReportStates.editing_volume)

    data = await state.get_data()
    items = [ReportItem(**it) for it in data.get("matched_items", [])]
    target_it = items[idx]

    await call.message.edit_text(
        f"✏️ *Позиция:* {target_it.position.name}\n"
        f"Текущий объем: *{target_it.volume} {target_it.unit}*\n\n"
        f"Введите новое значение объема (число):",
        parse_mode="Markdown"
    )


@report_router.message(ReportStates.editing_volume)
async def handle_save_edited_volume(message: Message, state: FSMContext):
    val_str = message.text.strip().replace(",", ".")
    try:
        new_vol = float(val_str)
        if new_vol <= 0:
            await message.answer("Объем должен быть положительным числом. Попробуйте снова:")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (например: 15 или 24.5):")
        return

    data = await state.get_data()
    idx = data.get("editing_item_idx", 0)
    matched_list = data.get("matched_items", [])

    if idx < len(matched_list):
        it = ReportItem(**matched_list[idx])
        it.volume = new_vol
        it.is_over_limit = new_vol > it.position.remaining_qty if it.position.remaining_qty > 0 else False
        it.over_limit_amount = max(0.0, new_vol - it.position.remaining_qty) if it.is_over_limit else 0.0
        it.warning_msg = f"Превышение сметы на {it.over_limit_amount} {it.unit}" if it.is_over_limit else None
        matched_list[idx] = it.model_dump()

    await state.update_data(matched_items=matched_list)
    await state.set_state(ReportStates.confirming_report)

    items_objs = [ReportItem(**it) for it in matched_list]
    today = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))
    text_preview = format_report_preview(items_objs, today)
    await message.answer(
        text_preview, 
        parse_mode="Markdown", 
        reply_markup=get_confirmation_keyboard(has_items=True)
    )


@report_router.callback_query(ReportStates.confirming_report, F.data == "btn_delete_item")
async def handle_start_delete(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = [ReportItem(**it) for it in data.get("matched_items", [])]
    await call.message.edit_text(
        "🗑 *Выберите позицию, которую хотите удалить из отчета:*",
        parse_mode="Markdown",
        reply_markup=get_item_select_keyboard(items, action_prefix="select_del")
    )


@report_router.callback_query(ReportStates.confirming_report, F.data.startswith("select_del_"))
async def handle_confirm_delete(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.replace("select_del_", ""))
    data = await state.get_data()
    matched_list = data.get("matched_items", [])

    if idx < len(matched_list):
        deleted = matched_list.pop(idx)
        logger.info(f"Удалена позиция: {deleted.get('position', {}).get('name')}")

    await state.update_data(matched_items=matched_list)
    items_objs = [ReportItem(**it) for it in matched_list]
    today = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))
    text_preview = format_report_preview(items_objs, today)
    await call.message.edit_text(
        text_preview, 
        parse_mode="Markdown", 
        reply_markup=get_confirmation_keyboard(has_items=bool(items_objs))
    )


@report_router.callback_query(ReportStates.confirming_report, F.data == "btn_add_item")
async def handle_start_add_item(call: CallbackQuery, state: FSMContext):
    await state.set_state(ReportStates.adding_item_select)
    await call.message.answer(
        "➕ *Добавление позиции в отчёт:*\n\n"
        "Введите название позиции и объем (например: «_шпилька 10 шт_» или «_кабель 3х1,5 25 м_»):",
        parse_mode="Markdown"
    )


@report_router.message(ReportStates.adding_item_select)
async def handle_add_item_input(
    message: Message, 
    state: FSMContext,
    catalog_service: CatalogService,
    llm_service: LLMService
):
    text = message.text.strip()
    positions = catalog_service.get_all()
    extraction = llm_service.extract_report_items(text, positions)

    data = await state.get_data()
    matched_list = data.get("matched_items", [])

    if extraction.matched_items:
        for it in extraction.matched_items:
            matched_list.append(it.model_dump())
        await message.answer(f"✅ Добавлено позиций: {len(extraction.matched_items)}")
    else:
        await message.answer("⚠️ Не удалось распознать позицию. Попробуйте еще раз.")
        return

    await state.update_data(matched_items=matched_list)
    await state.set_state(ReportStates.confirming_report)
    items_objs = [ReportItem(**it) for it in matched_list]
    today = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))
    text_preview = format_report_preview(items_objs, today)
    await message.answer(
        text_preview, 
        parse_mode="Markdown", 
        reply_markup=get_confirmation_keyboard(has_items=True)
    )


@report_router.callback_query(F.data == "back_to_confirm")
async def handle_back_to_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    matched_list = data.get("matched_items", [])
    items_objs = [ReportItem(**it) for it in matched_list]
    today = datetime.date.fromisoformat(data.get("report_date", datetime.date.today().isoformat()))
    text_preview = format_report_preview(items_objs, today)
    await call.message.edit_text(
        text_preview, 
        parse_mode="Markdown", 
        reply_markup=get_confirmation_keyboard(has_items=bool(items_objs))
    )

