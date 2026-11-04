import os
import datetime
import logging
import json
from typing import List, Optional, Tuple, Dict, Any
import openpyxl
import aiohttp
import requests

from config.settings import settings
from models.schemas import CatalogPosition, ReportItem

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """Сервис взаимодействия с Google Sheets (Service Account / Apps Script / Local Excel)."""

    def __init__(self):
        self.sa_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
        self.spreadsheet_id = settings.GOOGLE_SPREADSHEET_ID
        self.worksheet_name = settings.GOOGLE_WORKSHEET_NAME
        self.sheet_url = settings.GOOGLE_SHEET_URL
        self.apps_script_url = settings.GOOGLE_APPS_SCRIPT_URL or os.getenv("GOOGLE_APPS_SCRIPT_URL")
        self._client = None
        self._worksheet = None

    def is_configured(self) -> bool:
        """Проверяет, настроены ли реальные реквизиты Google Sheets."""
        has_apps_script = bool(self.apps_script_url and self.apps_script_url.startswith("http"))
        has_sa = bool(
            self.sa_file 
            and os.path.exists(self.sa_file) 
            and self.spreadsheet_id 
            and "your_google" not in self.spreadsheet_id
        )
        return has_apps_script or has_sa

    def load_positions_from_sheet(self) -> List[CatalogPosition]:
        """Загружает позиции из Google Sheets (gspread) или из локального файла Excel."""
        ws = self._get_worksheet()
        if not ws:
            from services.catalog_service import CatalogService
            return CatalogService(excel_path=settings.LOCAL_EXCEL_PATH).load_from_excel()

        try:
            from services.catalog_service import generate_aliases
            records = ws.get_all_values()
            positions = []
            current_section = "ОВ 3"
            for r_idx, row in enumerate(records, start=1):
                if r_idx < 4:
                    continue
                c1 = row[0] if len(row) > 0 else ""
                c2 = row[1] if len(row) > 1 else ""
                c3 = row[2] if len(row) > 2 else ""
                c4 = row[3] if len(row) > 3 else ""
                c5 = row[4] if len(row) > 4 else ""
                c6 = row[5] if len(row) > 5 else ""
                c9 = row[8] if len(row) > 8 else ""

                if c2 and not c3:
                    txt = str(c2).strip()
                    if "ОВ" in txt or "ЭМ" in txt:
                        current_section = txt
                        continue

                if c2 and c3:
                    name_clean = str(c2).strip()
                    if "ИТОГО" in name_clean.upper():
                        continue
                    try:
                        plan = float(str(c4).replace(",", ".").strip() or 0)
                    except ValueError:
                        plan = 0.0
                    try:
                        price = float(str(c5).replace(",", ".").strip() or 0)
                    except ValueError:
                        price = 0.0
                    try:
                        tot = float(str(c6).replace(",", ".").strip() or 0)
                    except ValueError:
                        tot = 0.0
                    try:
                        done = float(str(c9).replace(",", ".").strip() or 0)
                    except ValueError:
                        done = 0.0

                    rem = max(0.0, plan - done)
                    unit_clean = str(c3).strip()
                    aliases = generate_aliases(name_clean, current_section, unit_clean)

                    pos = CatalogPosition(
                        row_idx=r_idx,
                        section=current_section,
                        item_num=str(c1) if c1 else None,
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
            return positions
        except Exception as e:
            logger.error(f"Ошибка загрузки позиций из Google Sheets через gspread: {e}")
            from services.catalog_service import CatalogService
            return CatalogService(excel_path=settings.LOCAL_EXCEL_PATH).load_from_excel()

    def _get_worksheet(self):
        """Ленивая инициализация gspread клиента и листа."""
        if self._worksheet is not None:
            return self._worksheet

        if not (self.sa_file and os.path.exists(self.sa_file) and self.spreadsheet_id):
            return None

        try:
            import gspread
            self._client = gspread.service_account(filename=self.sa_file)
            sh = self._client.open_by_key(self.spreadsheet_id)
            try:
                self._worksheet = sh.worksheet(self.worksheet_name)
            except Exception:
                self._worksheet = sh.get_worksheet(0)
            return self._worksheet
        except Exception as e:
            logger.error(f"Ошибка подключения gspread к Google Sheets: {e}")
            return None

    def get_sheet_link(self) -> str:
        """Возвращает прямую ссылку на таблицу."""
        if self.sheet_url and "your_google" not in self.sheet_url:
            return self.sheet_url
        if self.spreadsheet_id and "your_google" not in self.spreadsheet_id:
            return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"
        return "https://docs.google.com/spreadsheets/"

    def get_or_create_date_column(self, date_target: datetime.date) -> int:
        ws = self._get_worksheet()
        if not ws:
            raise RuntimeError("Google Sheets не подключен")

        row3 = ws.row_values(3)
        date_str_dot = date_target.strftime("%d.%m.%Y")
        date_str_dash = date_target.strftime("%Y-%m-%d")
        date_str_short = date_target.strftime("%d.%m")

        for col_idx in range(10, len(row3) + 1):
            val = str(row3[col_idx - 1]).strip()
            if any(fmt in val for fmt in [date_str_dot, date_str_dash, date_str_short]):
                return col_idx

        new_col_idx = max(len(row3) + 1, 10)
        ws.update_cell(3, new_col_idx, date_str_dot)
        ws.update_cell(4, new_col_idx, "объем")
        return new_col_idx

    def record_volumes(self, items: List[ReportItem], date_target: Optional[datetime.date] = None) -> Tuple[bool, str]:
        target_date = date_target or datetime.date.today()

        # Вариант 1: Через Google Apps Script Webhook (если настроен)
        if self.apps_script_url and self.apps_script_url.startswith("http"):
            try:
                payload = {
                    "date": target_date.strftime("%d.%m.%Y"),
                    "items": [
                        {
                            "row_idx": it.position.row_idx,
                            "volume": it.volume,
                            "name": it.position.name
                        } for it in items
                    ]
                }
                resp = requests.post(self.apps_script_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return True, "Успешно записано в Google Sheets через Webhook"
            except Exception as e:
                logger.warning(f"Ошибка Apps Script Webhook: {e}")

        # Вариант 2: Через Service Account (gspread)
        ws = self._get_worksheet()
        if ws:
            try:
                col_idx = self.get_or_create_date_column(target_date)
                for item in items:
                    ws.update_cell(item.position.row_idx, col_idx, item.volume)
                return True, f"Успешно записано в Google Sheets (столбец {col_idx})"
            except Exception as e:
                logger.error(f"Ошибка записи gspread: {e}")

        # Вариант 3: Резервная запись в локальный Excel
        return self.record_volumes_local_excel(items, target_date)

    def get_today_entries(self, date_target: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
        target_date = date_target or datetime.date.today()
        ws = self._get_worksheet()
        if ws:
            try:
                col_idx = self.get_or_create_date_column(target_date)
                col_values = ws.col_values(col_idx)
                entries = []
                for r_idx, val in enumerate(col_values, start=1):
                    if r_idx < 5:
                        continue
                    clean_val = str(val).strip().replace(",", ".")
                    try:
                        vol = float(clean_val)
                        if vol > 0:
                            entries.append({"row_idx": r_idx, "volume": vol})
                    except ValueError:
                        continue
                return entries
            except Exception as e:
                logger.error(f"Ошибка чтения данных gspread: {e}")

        return self.get_today_entries_local_excel(target_date)

    def record_volumes_local_excel(self, items: List[ReportItem], date_target: datetime.date) -> Tuple[bool, str]:
        file_path = settings.LOCAL_EXCEL_PATH
        if not os.path.exists(file_path):
            return False, f"Файл {file_path} не найден"

        try:
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active
            target_str = date_target.strftime("%Y-%m-%d")
            col_idx = None

            for c in range(10, ws.max_column + 1):
                cell_val = ws.cell(3, c).value
                if cell_val:
                    if isinstance(cell_val, (datetime.datetime, datetime.date)):
                        if cell_val.strftime("%Y-%m-%d") == target_str:
                            col_idx = c
                            break
                    elif target_str in str(cell_val) or date_target.strftime("%d.%m") in str(cell_val):
                        col_idx = c
                        break

            if col_idx is None:
                col_idx = max(ws.max_column + 1, 10)
                ws.cell(3, col_idx).value = datetime.datetime.combine(date_target, datetime.time.min)
                ws.cell(3, col_idx).number_format = 'yyyy-mm-dd'
                ws.cell(4, col_idx).value = "объем"

            for it in items:
                ws.cell(it.position.row_idx, col_idx).value = it.volume

            wb.save(file_path)
            return True, f"Записано в локальную таблицу (столбец {col_idx})"
        except Exception as e:
            return False, str(e)

    def get_today_entries_local_excel(self, date_target: datetime.date) -> List[Dict[str, Any]]:
        file_path = settings.LOCAL_EXCEL_PATH
        if not os.path.exists(file_path):
            return []

        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        target_str = date_target.strftime("%Y-%m-%d")
        col_idx = None

        for c in range(10, ws.max_column + 1):
            cell_val = ws.cell(3, c).value
            if cell_val:
                if isinstance(cell_val, (datetime.datetime, datetime.date)):
                    if cell_val.strftime("%Y-%m-%d") == target_str:
                        col_idx = c
                        break
                elif target_str in str(cell_val) or date_target.strftime("%d.%m") in str(cell_val):
                    col_idx = c
                    break

        if col_idx is None:
            return []

        entries = []
        for r in range(5, ws.max_row + 1):
            val = ws.cell(r, col_idx).value
            if val is not None and isinstance(val, (int, float)) and val > 0:
                entries.append({"row_idx": r, "volume": float(val)})
        return entries
