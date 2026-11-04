import unittest
import os
import sys
import datetime
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.catalog_service import CatalogService
from services.sheets_service import GoogleSheetsService
from services.bitrix_service import Bitrix24Service
from models.schemas import ReportItem


class TestServices(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CatalogService()
        cls.positions = cls.catalog.load_from_excel()
        cls.sheets = GoogleSheetsService()
        cls.bitrix = Bitrix24Service()

    def test_catalog_loaded(self):
        self.assertEqual(len(self.positions), 62)
        pos_17 = self.catalog.get_by_row(17)
        self.assertIsNotNone(pos_17)
        self.assertIn("6,35", pos_17.name)
        self.assertEqual(pos_17.unit, "м")

    def test_local_excel_write_and_read(self):
        """Тест записи объемов в дату и последующего чтения за сегодня."""
        # Создаем временную копию Excel, чтобы не затронуть оригинальный файл
        temp_file = "test_temp_sheet.xlsx"
        shutil.copy("Ежедневное_выполнение_Садик.xlsx", temp_file)

        try:
            self.sheets.LOCAL_EXCEL_PATH = temp_file
            # Подменяем путь в settings
            from config.settings import settings
            orig_path = settings.LOCAL_EXCEL_PATH
            settings.LOCAL_EXCEL_PATH = temp_file

            pos = self.catalog.get_by_row(17)
            item = ReportItem(
                position=pos,
                volume=42.5,
                unit="м",
                raw_text="тест записи"
            )
            today = datetime.date.today()

            ok, msg = self.sheets.record_volumes_local_excel([item], today)
            self.assertTrue(ok)

            # Читаем обратно
            entries = self.sheets.get_today_entries_local_excel(today)
            self.assertTrue(any(e["row_idx"] == 17 and e["volume"] == 42.5 for e in entries))

            settings.LOCAL_EXCEL_PATH = orig_path
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def test_bitrix_simulation(self):
        """Тест формирования отчета для Битрикс24 в симуляционном режиме."""
        pos = self.catalog.get_by_row(17)
        item = ReportItem(
            position=pos,
            volume=15.0,
            unit="м",
            raw_text="медь 6-ка 15 м"
        )
        res = await self.bitrix.send_report(
            items=[item],
            master_name="Тестовый мастер"
        )
        self.assertTrue(res.get("success"))


if __name__ == "__main__":
    unittest.main()

