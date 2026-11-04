import logging
from aiogram import Router, F
from aiogram.types import Message
from services.catalog_service import CatalogService
from utils.text_matcher import RuleMatcher

logger = logging.getLogger(__name__)
questions_router = Router(name="questions_router")


def format_position_balance(p) -> str:
    pct = (p.completed_qty / p.plan_qty * 100) if p.plan_qty > 0 else 0.0
    return (
        f"📌 *{p.name}*\n"
        f"• Раздел: _{p.section}_\n"
        f"• Сметный объем: *{p.plan_qty} {p.unit}*\n"
        f"• Выполнено ранее: *{p.completed_qty} {p.unit}* ({pct:.1f}%)\n"
        f"• 🟢 *Остаток по смете:* *{p.remaining_qty} {p.unit}*\n"
        f"• Расценка (ЗП): *{p.price_per_unit} руб./{p.unit}*"
    )


@questions_router.message(F.text.regexp(r'(?i)(?:сколько|какой|каков)\s+(?:осталось|остаток)'))
async def handle_balance_question(message: Message, catalog_service: CatalogService):
    text = message.text.strip()
    positions = catalog_service.get_all()

    candidates = RuleMatcher.find_candidates(text, positions)

    if not candidates:
        await message.answer(
            "🔍 Не удалось найти подходящую позицию в смете по вашему запросу. "
            "Попробуйте уточнить запрос, например: «_сколько осталось по кабелю 3х2,5?_»",
            parse_mode="Markdown"
        )
        return

    # Если найдено несколько близких вариантов с высоким скором (например все кабели)
    top_candidates = [c[0] for c in candidates if c[1] >= 80.0]
    if len(top_candidates) > 1:
        resp_lines = ["🔍 *Найдено несколько подходящих позиций по вашему вопросу:*\n"]
        for p in top_candidates[:5]:
            resp_lines.append(format_position_balance(p))
            resp_lines.append("─────────────────────────")
        await message.answer("\n".join(resp_lines), parse_mode="Markdown")
        return

    # Одиночное точное совпадение
    best_match = candidates[0][0]
    await message.answer(format_position_balance(best_match), parse_mode="Markdown")

