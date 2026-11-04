from aiogram.fsm.state import State, StatesGroup


class ReportStates(StatesGroup):
    waiting_input = State()              # Ожидание текстового или голосового отчета
    confirming_report = State()          # Просмотр распознанного списка и подтверждение
    clarifying_ambiguous = State()       # Уточнение спорной позиции из предложенных вариантов
    editing_volume = State()             # Ввод нового объема для конкретной позиции
    adding_item_select = State()         # Выбор позиции при ручном добавлении
    adding_item_volume = State()         # Ввод объема при ручном добавлении
    editing_today_select = State()       # Выбор позиции для корректировки данных за сегодня
    editing_today_volume = State()       # Ввод нового объема для записи за сегодня

