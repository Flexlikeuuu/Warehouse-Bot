from typing import List, Optional
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton
)
from models.schemas import ReportItem, AmbiguousCandidate, CatalogPosition


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура бота."""
    kb = [
        [KeyboardButton(text="📝 Новый отчёт"), KeyboardButton(text="📋 Данные за сегодня")],
        [KeyboardButton(text="📊 Ссылка на таблицу"), KeyboardButton(text="ℹ️ Справка / Команды")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_confirmation_keyboard(has_items: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения дневного отчета."""
    buttons = []
    if has_items:
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить и записать", callback_data="confirm_save")])
        buttons.append([
            InlineKeyboardButton(text="✏️ Изменить объём", callback_data="btn_edit_volume"),
            InlineKeyboardButton(text="➕ Добавить", callback_data="btn_add_item")
        ])
        buttons.append([
            InlineKeyboardButton(text="🗑 Удалить позицию", callback_data="btn_delete_item"),
            InlineKeyboardButton(text="❌ Отменить всё", callback_data="btn_cancel_report")
        ])
    else:
        buttons.append([InlineKeyboardButton(text="➕ Добавить позицию", callback_data="btn_add_item")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="btn_cancel_report")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_clarification_keyboard(candidates: List[AmbiguousCandidate]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора одного из спорных вариантов позиции."""
    buttons = []
    for c in candidates:
        btn_text = f"#{c.row_idx} {c.name[:35]}... ({c.unit})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"clarify_pick_{c.row_idx}")])

    buttons.append([InlineKeyboardButton(text="🚫 Пропустить эту позицию", callback_data="clarify_skip")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_item_select_keyboard(items: List[ReportItem], action_prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора позиции из текущего списка (для редактирования или удаления)."""
    buttons = []
    for idx, it in enumerate(items):
        txt = f"{idx + 1}. {it.position.name[:30]} ({it.volume} {it.unit})"
        buttons.append([InlineKeyboardButton(text=txt, callback_data=f"{action_prefix}_{idx}")])

    buttons.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_post_save_keyboard(sheet_url: Optional[str] = None, task_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура после успешной записи отчета."""
    buttons = []
    if sheet_url and sheet_url.startswith("http"):
        buttons.append([InlineKeyboardButton(text="📊 Открыть Google Таблицу", url=sheet_url)])
    if task_url and task_url.startswith("http"):
        buttons.append([InlineKeyboardButton(text="🏢 Открыть задачу в Битрикс24", url=task_url)])

    buttons.append([InlineKeyboardButton(text="📝 Внести ещё данные", callback_data="btn_new_entry")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_today_entries_keyboard(entries_count: int) -> InlineKeyboardMarkup:
    """Клавиатура для управления уже внесенными данными за сегодня."""
    buttons = []
    for i in range(entries_count):
        buttons.append([InlineKeyboardButton(text=f"✏️ Изменить позицию #{i+1}", callback_data=f"edit_today_{i}")])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

