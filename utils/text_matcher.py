import re
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz, process
from models.schemas import CatalogPosition, AmbiguousCandidate


class RuleMatcher:
    """Детерминированный сопоставитель разговорных фраз с позициями каталога."""

    @staticmethod
    def find_candidates(query: str, positions: List[CatalogPosition]) -> List[Tuple[CatalogPosition, float]]:
        """
        Ищет кандидатов на основе точного совпадения алиасов, нормализованных чисел/сечений
        и fuzzy-сравнения. Возвращает список (CatalogPosition, score).
        """
        q_clean = query.lower().strip()
        results: List[Tuple[CatalogPosition, float]] = []

        # 1. Проверка по алиасам (приоритет 100)
        for p in positions:
            for alias in p.aliases:
                if alias == q_clean:
                    results.append((p, 100.0))
                    break
                elif alias in q_clean or q_clean in alias:
                    # Частичное вхождение алиаса
                    score = 90.0 if len(alias) > 3 else 75.0
                    results.append((p, score))
                    break

        if results and results[0][1] >= 90.0:
            # Сортируем по убыванию скора
            results.sort(key=lambda x: x[1], reverse=True)
            return results

        # 2. Нечеткое сравнение (RapidFuzz) по названию и алиасам
        for p in positions:
            best_score = fuzz.token_set_ratio(q_clean, p.name.lower())
            for alias in p.aliases:
                al_score = fuzz.ratio(q_clean, alias)
                if al_score > best_score:
                    best_score = al_score
            if best_score >= 60.0:
                results.append((p, float(best_score)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    @staticmethod
    def detect_ambiguity(query: str, positions: List[CatalogPosition]) -> Optional[List[AmbiguousCandidate]]:
        """
        Определяет, является ли запрос заведомо неоднозначным.
        Например, 'хомут 10 шт' или 'кабель 50 м'.
        """
        q_lower = query.lower()

        # Хомуты без конкретизации (фреон vs дренаж)
        if "хомут" in q_lower and "фреон" not in q_lower and "дренаж" not in q_lower and "32" not in q_lower and "25" not in q_lower:
            candidates = [p for p in positions if "хомут" in p.name.lower()]
            return [
                AmbiguousCandidate(
                    row_idx=c.row_idx,
                    name=c.name,
                    section=c.section,
                    unit=c.unit,
                    remaining_qty=c.remaining_qty
                ) for c in candidates
            ]

        # Кабель без указания сечения
        if "кабель" in q_lower and not re.search(r'\d+\s*[xх]\s*[\d,\.]+', q_lower):
            cables = [p for p in positions if "кабель силовой" in p.name.lower()]
            return [
                AmbiguousCandidate(
                    row_idx=c.row_idx,
                    name=c.name,
                    section=c.section,
                    unit=c.unit,
                    remaining_qty=c.remaining_qty
                ) for c in cables[:4]
            ]

        # Медь / фреонопровод без диаметра
        if ("медь" in q_lower or "фреонопровод" in q_lower) and not any(d in q_lower for d in ["6", "9", "12", "шест", "девят", "двен"]):
            copper = [p for p in positions if "фреонопровод медный" in p.name.lower()]
            return [
                AmbiguousCandidate(
                    row_idx=c.row_idx,
                    name=c.name,
                    section=c.section,
                    unit=c.unit,
                    remaining_qty=c.remaining_qty
                ) for c in copper
            ]

        return None

