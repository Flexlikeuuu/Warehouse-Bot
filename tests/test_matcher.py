import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.catalog_service import CatalogService
from services.llm_service import LLMService
from utils.text_matcher import RuleMatcher


class TestMatcherAndExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CatalogService()
        cls.positions = cls.catalog.load_from_excel()
        cls.llm = LLMService()

    def test_sample_from_specification(self):
        """Проверка эталонного примера из текста ТЗ."""
        text = "Сегодня проложили медь 6-ку 15 м и 9-ку 15 м, изоляцию на них столько же, кабель 3х2,5 — 56 м, поставили 10 хомутов под фреон"
        result = self.llm.extract_report_items(text, self.positions)

        self.assertFalse(result.is_question)
        self.assertEqual(len(result.matched_items), 6)

        # Проверяем строки
        row_indices = [it.position.row_idx for it in result.matched_items]
        self.assertIn(17, row_indices)  # Медь 6,35
        self.assertIn(18, row_indices)  # Медь 9,52
        self.assertIn(20, row_indices)  # Изоляция 6,35
        self.assertIn(21, row_indices)  # Изоляция 9,52
        self.assertIn(55, row_indices)  # Кабель 3х2,5
        self.assertIn(44, row_indices)  # Хомуты фреон

        # Проверяем объемы
        vol_by_row = {it.position.row_idx: it.volume for it in result.matched_items}
        self.assertEqual(vol_by_row[17], 15.0)
        self.assertEqual(vol_by_row[18], 15.0)
        self.assertEqual(vol_by_row[20], 15.0)  # "столько же"
        self.assertEqual(vol_by_row[21], 15.0)  # "столько же"
        self.assertEqual(vol_by_row[55], 56.0)
        self.assertEqual(vol_by_row[44], 10.0)

    def test_ambiguity_handling(self):
        """Проверка выявления неоднозначности: хомуты без указания типа."""
        text = "Сегодня поставили 10 хомутов"
        result = self.llm.extract_report_items(text, self.positions)

        self.assertEqual(len(result.ambiguous_items), 1)
        ambig = result.ambiguous_items[0]
        cand_rows = [c.row_idx for c in ambig.candidates]
        self.assertIn(43, cand_rows)  # Хомут дренажа 25мм
        self.assertIn(44, cand_rows)  # Хомут фреона 32мм

    def test_question_answering(self):
        """Проверка распознавания вопроса по остаткам."""
        text = "Сколько осталось по кабелю 3х2,5?"
        result = self.llm.extract_report_items(text, self.positions)

        self.assertTrue(result.is_question)
        self.assertEqual(result.target_row_idx, 55)

    def test_over_limit_warning(self):
        """Проверка генерации предупреждения при превышении сметы."""
        pos = self.catalog.get_by_row(17)
        # У позиции 17 остаток 125 м. Задаем объем 200 м
        text = "медь 6-ку 200 м"
        result = self.llm.extract_report_items(text, self.positions)
        self.assertEqual(len(result.matched_items), 1)
        item = result.matched_items[0]
        self.assertTrue(item.is_over_limit)
        self.assertGreater(item.over_limit_amount, 0)
        self.assertIsNotNone(item.warning_msg)


if __name__ == "__main__":
    unittest.main()

