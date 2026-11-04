import re
import logging
from typing import List, Optional, Dict
import openpyxl
from models.schemas import CatalogPosition

logger = logging.getLogger(__name__)


def generate_aliases(name: str, section: str, unit: str) -> List[str]:
    """Генерирует разговорные синонимы/жаргонизмы для позиции спецификации."""
    aliases = set()
    name_lower = name.lower()

    # Фреонопроводы медные
    if "фреонопровод" in name_lower or "медь" in name_lower:
        if "6,35" in name_lower or "6.35" in name_lower:
            aliases.update([
                "медь 6", "медь 6-ка", "медь 6-ку", "медь шестерка", "шестерка", 
                "шестерку", "6-ка", "6-ку", "фреонопровод 6", "фреон 6", "д6.35", "д6,35"
            ])
        elif "9,52" in name_lower or "9.52" in name_lower:
            aliases.update([
                "медь 9", "медь 9-ка", "медь 9-ку", "медь девятка", "девятка", 
                "девятку", "9-ка", "9-ку", "фреонопровод 9", "фреон 9", "д9.52", "д9,52"
            ])
        elif "12.7" in name_lower or "12,7" in name_lower:
            aliases.update([
                "медь 12", "медь 12-ка", "медь 12-ку", "двенашка", "двенашку", 
                "12-ка", "12-ку", "фреонопровод 12", "фреон 12", "д12.7", "д12,7",
                "12-я медь", "12-ю медь", "12 медь"
            ])

    # Теплоизоляция (трубка K-FLEX)
    if "теплоизоляционная" in name_lower or "изоляция" in name_lower or "k-flex" in name_lower:
        if "6,35" in name_lower or "6.35" in name_lower:
            aliases.update([
                "изоляция 6", "изоляция 6-ка", "изоляция 6-ку", "изоляция на 6", 
                "флекс 6", "к-флекс 6", "теплоизоляция 6", "изоляция шестерка"
            ])
        elif "9,52" in name_lower or "9.52" in name_lower:
            aliases.update([
                "изоляция 9", "изоляция 9-ка", "изоляция 9-ку", "изоляция на 9", 
                "флекс 9", "к-флекс 9", "теплоизоляция 9", "изоляция девятка"
            ])
        elif "12.7" in name_lower or "12,7" in name_lower:
            aliases.update([
                "изоляция 12", "изоляция 12-ка", "изоляция 12-ку", "изоляция на 12", 
                "флекс 12", "к-флекс 12", "теплоизоляция 12", "изоляция двенашка"
            ])

    # Кабели силовые
    if "кабель" in name_lower:
        # Извлекаем сечения: 3х2,5, 3х1,5, 4х1,5, 3х4, 5х6, 2х1,5
        m = re.search(r'(\d+)\s*[xх]\s*([\d,\.]+)', name_lower)
        if m:
            sec_orig = f"{m.group(1)}х{m.group(2).replace('.', ',')}"
            sec_dot = f"{m.group(1)}x{m.group(2).replace(',', '.')}"
            sec_sp = f"{m.group(1)} на {m.group(2).replace('.', ',')}"
            sec_num = f"{m.group(1)} {m.group(2)}"
            aliases.update([
                f"кабель {sec_orig}", f"кабель {sec_dot}", f"кабель {sec_sp}",
                sec_orig, sec_dot, sec_sp, sec_num, f"силовой {sec_orig}"
            ])

    # Хомуты
    if "хомут" in name_lower:
        if "фреон" in name_lower:
            aliases.update([
                "хомут под фреон", "хомуты под фреон", "хомут фреон", "хомуты фреон", 
                "фреоновый хомут", "фреоновые хомуты", "хомут 32", "хомуты 32"
            ])
        elif "дренаж" in name_lower:
            aliases.update([
                "хомут под дренаж", "хомуты под дренаж", "хомут дренаж", "хомуты дренаж", 
                "дренажный хомут", "дренажные хомуты", "хомут 25", "хомуты 25"
            ])

    # Трубы ПВХ
    if "труба пвх" in name_lower:
        if "20" in name_lower:
            aliases.update([
                "труба пвх 20", "пвх 20", "двадцатка труба", "гофра 20", "пвх 20мм",
                "труба пвх двадцатка", "трубу пвх двадцатку", "пвх двадцатка", "пвх двадцатку", "двадцатка", "двадцатку"
            ])
        elif "25" in name_lower:
            aliases.update(["труба пвх 25", "пвх 25", "пвх 25мм"])

    # Шпильки
    if "шпилька" in name_lower:
        aliases.update([
            "шпилька", "шпильки", "шпилек", "шпилька м8", "шпильки м8", "шпилек м8"
        ])

    # Автоматы (Установка АВ на DIN-рейку)
    if "ав" in name_lower or "din" in name_lower or "дин" in name_lower or "автомат" in name_lower:
        aliases.update([
            "автомат", "автоматы", "автомата", "автоматов", "автомат на дин-рейку", 
            "автоматы на дин-рейку", "автомата на дин-рейку", "установка ав", "установка ав на din-рейку"
        ])

    # Короба
    if "короб" in name_lower:
        if "металлически" in name_lower or "150х60" in name_lower:
            aliases.update(["короб металлический", "короб металл", "металлический короб", "короб 150х60"])
        elif "пвх" in name_lower or "angara" in name_lower or "90х60" in name_lower:
            aliases.update(["короб пвх 90х60", "короб ангара", "короб angara", "короб 90х60"])
        elif "25х16" in name_lower:
            aliases.update(["короб 25х16", "кабель-канал 25х16", "короб пвх 25х16"])

    # Дренажные насосы / помпы
    if "насос" in name_lower or "помпа" in name_lower:
        if "sauermann" in name_lower:
            aliases.update(["помпа зауерман", "помпа sauermann", "дренажная помпа sauermann", "помпа si 33"])
        elif "aspen" in name_lower:
            aliases.update(["насос аспен", "насос aspen", "дренажный насос aspen"])

    # Сверление отверстий
    if "сверлен" in name_lower or "сберлен" in name_lower:
        aliases.update(["сверление", "сверление отверстий", "бурение отверстий", "отверстия д80"])

    # Прокладка кабеля
    if "прокладка силовых кабелей" in name_lower:
        if "в трубе" in name_lower:
            aliases.update(["прокладка кабеля в трубе", "кабель в трубе", "протяжка в трубе"])
        elif "в коробе" in name_lower:
            aliases.update(["прокладка кабеля в коробе", "кабель в коробе", "протяжка в коробе"])
        elif "на скобах" in name_lower:
            aliases.update(["прокладка кабеля на скобах", "кабель на скобах"])

    return list(aliases)


class CatalogService:
    """Управляет динамическим справочником позиций спецификации."""

    def __init__(self, excel_path: str = "Ежедневное_выполнение_Садик.xlsx"):
        self.excel_path = excel_path
        self._positions: List[CatalogPosition] = []
        self._by_row_idx: Dict[int, CatalogPosition] = {}

    def load_from_excel(self, file_path: Optional[str] = None) -> List[CatalogPosition]:
        """Загружает справочник позиций из Excel-файла."""
        path = file_path or self.excel_path
        logger.info(f"Загрузка справочника позиций из {path}")

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active

        positions = []
        current_section = "ОВ 3"

        for r in range(4, ws.max_row + 1):
            c1 = ws.cell(r, 1).value
            c2 = ws.cell(r, 2).value
            c3 = ws.cell(r, 3).value
            c4 = ws.cell(r, 4).value
            c5 = ws.cell(r, 5).value
            c6 = ws.cell(r, 6).value
            c9 = ws.cell(r, 9).value

            # Заголовок раздела (например "ОВ 3" или "ЭМ3")
            if c2 and not c3:
                txt = str(c2).strip()
                if "ОВ" in txt or "ЭМ" in txt:
                    current_section = txt
                    continue

            # Строка спецификации (есть наименование и единица измерения)
            if c2 and c3:
                name_clean = str(c2).strip()
                # Исключаем итоговые строки
                if "ИТОГО" in name_clean.upper():
                    continue

                plan = float(c4) if isinstance(c4, (int, float)) else 0.0
                price = float(c5) if isinstance(c5, (int, float)) else 0.0
                tot = float(c6) if isinstance(c6, (int, float)) else 0.0
                done = float(c9) if isinstance(c9, (int, float)) else 0.0
                rem = max(0.0, plan - done)

                unit_clean = str(c3).strip()
                aliases = generate_aliases(name_clean, current_section, unit_clean)

                pos = CatalogPosition(
                    row_idx=r,
                    section=current_section,
                    item_num=str(c1) if c1 is not None else None,
                    name=name_clean,
                    unit=unit_clean,
                    plan_qty=plan,
                    price_per_unit=price,
                    total_price=tot,
                    completed_qty=done,
                    remaining_qty=rem,
                    aliases=aliases
                )
                positions.append(pos)

        self._positions = positions
        self._by_row_idx = {p.row_idx: p for p in positions}
        logger.info(f"Загружено {len(self._positions)} позиций из Excel")
        return self._positions

    def get_all(self) -> List[CatalogPosition]:
        if not self._positions:
            self.load_from_excel()
        return self._positions

    def get_by_row(self, row_idx: int) -> Optional[CatalogPosition]:
        if not self._positions:
            self.load_from_excel()
        return self._by_row_idx.get(row_idx)

    def update_completed_qty(self, row_idx: int, added_volume: float):
        """Локально обновляет выполненный объем и остаток (после записи в таблицу)."""
        pos = self.get_by_row(row_idx)
        if pos:
            pos.completed_qty += added_volume
            pos.remaining_qty = max(0.0, pos.plan_qty - pos.completed_qty)

    def set_positions_from_raw_data(self, positions: List[CatalogPosition]):
        """Обновление списка позиций напрямую (например, из Google Sheets)."""
        self._positions = positions
        self._by_row_idx = {p.row_idx: p for p in positions}

