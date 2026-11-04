import json
import logging
import re
from typing import List, Optional, Dict, Any
from config.settings import settings
from models.schemas import (
    CatalogPosition, ReportItem, AmbiguousItem, AmbiguousCandidate, 
    UnrecognizedItem, ExtractionResult
)
from utils.text_matcher import RuleMatcher

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Ты — интеллектуальный AI-ассистент прораба/мастера на строительном объекте.
Твоя задача — принимать дневные отчеты о выполненных строительно-монтажных работах (текстом или голосовой транскрипцией) и сопоставлять их с позициями сметной спецификации.

СПРАВОЧНИК ПОЗИЦИЙ СПЕЦИФИКАЦИИ (загружен динамически из таблицы):
{catalog_json}

ПРАВИЛА И ИНСТРУКЦИИ:
1. ПОНИМАНИЕ СТРОИТЕЛЬНОГО СЛЕНГА И ЖАРГОНИЗМОВ:
   - "медь 6-ка", "шестёрка", "медь 6" -> Фреонопровод медный Д6,35 (ряд 17).
   - "медь 9-ка", "девятка", "медь 9" -> Фреонопровод медный Д9,52 (ряд 18).
   - "медь 12-ка", "двенашка" -> Фреонопровод медный Д12.7 (ряд 19).
   - "изоляция на них столько же" -> Разрешение контекстной ссылки! Если перед этим проложили медь 6-ку 15 м и 9-ку 15 м, то нужно записать:
     * Трубка теплоизоляционная Д6,35 = 15 м (ряд 20)
     * Трубка теплоизоляционная Д9,52 = 15 м (ряд 21)
   - "кабель 3 на 2,5", "3х2.5", "силовой 3*2,5" -> Кабель силовой 3х2,5-0,66 (ряд 55).
   - "хомуты под фреон" -> Хомут для крепления фреонопровода М8 32 мм (ряд 44).
   - "хомуты под дренаж" -> Хомут для крепления дренажа М8 25мм (ряд 43).

2. НЕОДНОЗНАЧНОСТЬ (НЕ УГАДЫВАЙ!):
   - Если позиция не названа однозначно (например, просто "поставили 10 хомутов" без указания фреон/дренаж или "протянули 50 м кабеля" без сечения) — помести её в ambiguous_items со списком candidate_row_indices. Мастер должен уточнить сам!

3. ВОПРОСЫ ПО ОСТАТКАМ:
   - Если сообщение — это вопрос вида "сколько осталось по кабелю 3х2,5?", "какой остаток по меди?", установи is_question: true и укажи target_row_idx.

4. ФОРМАТ ОТВЕТА (ТОЛЬКО ЧИСТЫЙ JSON):
{{
  "is_question": false,
  "question_query": null,
  "target_row_idx": null,
  "matched_items": [
    {{
      "row_idx": 17,
      "volume": 15.0,
      "unit": "м",
      "raw_text": "медь 6-ку 15 м"
    }}
  ],
  "ambiguous_items": [
    {{
      "raw_text": "хомуты 10 шт",
      "volume": 10.0,
      "unit": "шт",
      "candidate_row_indices": [43, 44],
      "reason": "Уточните: хомут для дренажа или для фреонопровода?"
    }}
  ],
  "unrecognized_items": [
    {{
      "raw_text": "неизвестный материал",
      "volume": 5.0,
      "unit": "шт",
      "reason": "Не найдено в спецификации"
    }}
  ]
}}
"""


class LLMService:
    """Сервис извлечения сущностей из текста отчета с помощью Gemini или OpenAI (или fallback)."""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.gemini_key = settings.GEMINI_API_KEY
        self.gemini_client = None

        if self.gemini_key and (len(self.gemini_key) > 20):
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.gemini_key)
                logger.info("Инициализирован Google Gemini Client (Google AI Studio)")
            except Exception as e:
                logger.warning(f"Не удалось инициализировать Google Gemini: {e}")

        # OpenAI fallback client
        self.openai_key = settings.OPENAI_API_KEY
        self.openai_client = None
        if self.openai_key and "sk-" in self.openai_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.openai_key, base_url=settings.OPENAI_BASE_URL)
            except Exception as e:
                logger.warning(f"Не удалось инициализировать OpenAI: {e}")

    def extract_report_items(self, text: str, positions: List[CatalogPosition]) -> ExtractionResult:
        """Главный метод извлечения данных из свободного текста."""
        clean_text = text.strip()

        # 1. Проверяем, не является ли текст вопросом по остаткам (быстрый check)
        is_q, target_pos = self._check_is_question(clean_text, positions)
        if is_q and target_pos:
            return ExtractionResult(
                is_question=True,
                question_query=clean_text,
                target_row_idx=target_pos.row_idx,
                raw_input=clean_text
            )

        # 2. Попытка вызова Google Gemini (с перебором стабильных моделей при пиковых нагрузках)
        if self.gemini_client:
            models_to_try = [
                settings.GEMINI_MODEL,
                "gemini-3.5-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-3.8-flash",
                "gemini-flash-latest"
            ]
            seen = set()
            for mod in models_to_try:
                if not mod or mod in seen:
                    continue
                seen.add(mod)
                try:
                    return self._call_gemini_with_model(clean_text, positions, mod)
                except Exception as e:
                    logger.warning(f"Модель Gemini '{mod}' вернула ошибку ({e}), переключаемся на резервную модель...")
                    continue

        # 3. Попытка вызова OpenAI
        if self.openai_client:
            try:
                return self._call_openai(clean_text, positions)
            except Exception as e:
                logger.warning(f"Ошибка OpenAI API ({e}), переключение на резервный парсер...")

        # 4. Детерминированный fallback (работает всегда)
        return self._fallback_extract(clean_text, positions)

    def _call_gemini_with_model(self, text: str, positions: List[CatalogPosition], model_name: str) -> ExtractionResult:
        """Вызов Google Gemini с генерацией строгого JSON."""
        from google.genai import types

        catalog_summary = [
            {
                "row_idx": p.row_idx,
                "section": p.section,
                "name": p.name,
                "unit": p.unit,
                "rem": p.remaining_qty,
                "aliases": p.aliases
            }
            for p in positions
        ]

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            catalog_json=json.dumps(catalog_summary, ensure_ascii=False, indent=1)
        )

        response = self.gemini_client.models.generate_content(
            model=model_name,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.0
            )
        )

        content = response.text
        data = json.loads(content)
        return self._process_extracted_json(data, text, positions)

    def _call_openai(self, text: str, positions: List[CatalogPosition]) -> ExtractionResult:
        catalog_summary = [
            {
                "row_idx": p.row_idx,
                "section": p.section,
                "name": p.name,
                "unit": p.unit,
                "rem": p.remaining_qty,
                "aliases": p.aliases
            }
            for p in positions
        ]

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            catalog_json=json.dumps(catalog_summary, ensure_ascii=False, indent=1)
        )

        response = self.openai_client.chat.completions.create(
            model=settings.LLM_MODEL or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        data = json.loads(content)
        return self._process_extracted_json(data, text, positions)

    def _process_extracted_json(
        self, data: Dict[str, Any], raw_text: str, positions: List[CatalogPosition]
    ) -> ExtractionResult:
        pos_by_row = {p.row_idx: p for p in positions}

        matched: List[ReportItem] = []
        for m in data.get("matched_items", []):
            row_idx = m.get("row_idx")
            pos = pos_by_row.get(row_idx)
            if not pos:
                continue

            vol = float(m.get("volume", 0.0))
            is_over = vol > pos.remaining_qty if pos.remaining_qty > 0 else False
            over_amt = max(0.0, vol - pos.remaining_qty) if is_over else 0.0
            warn_msg = None
            if is_over:
                warn_msg = (
                    f"⚠️ Внимание: объем {vol} {pos.unit} превышает остаток по смете "
                    f"({pos.remaining_qty:.1f} {pos.unit}). Превышение: {over_amt:.1f} {pos.unit}."
                )

            item = ReportItem(
                position=pos,
                volume=vol,
                unit=m.get("unit") or pos.unit,
                raw_text=m.get("raw_text", ""),
                is_over_limit=is_over,
                over_limit_amount=over_amt,
                warning_msg=warn_msg
            )
            matched.append(item)

        ambiguous: List[AmbiguousItem] = []
        for a in data.get("ambiguous_items", []):
            candidate_rows = a.get("candidate_row_indices", [])
            cand_objects = []
            for r in candidate_rows:
                cp = pos_by_row.get(r)
                if cp:
                    cand_objects.append(
                        AmbiguousCandidate(
                            row_idx=cp.row_idx,
                            name=cp.name,
                            section=cp.section,
                            unit=cp.unit,
                            remaining_qty=cp.remaining_qty
                        )
                    )

            ambiguous.append(
                AmbiguousItem(
                    raw_text=a.get("raw_text", ""),
                    volume=float(a.get("volume", 0.0)),
                    unit=a.get("unit", "шт"),
                    candidates=cand_objects,
                    reason=a.get("reason", "Требуется уточнение позиции")
                )
            )

        unrecognized: List[UnrecognizedItem] = [
            UnrecognizedItem(
                raw_text=u.get("raw_text", ""),
                volume=u.get("volume"),
                unit=u.get("unit"),
                reason=u.get("reason", "Не найдено в спецификации")
            )
            for u in data.get("unrecognized_items", [])
        ]

        return ExtractionResult(
            is_question=bool(data.get("is_question", False)),
            question_query=data.get("question_query"),
            target_row_idx=data.get("target_row_idx"),
            matched_items=matched,
            ambiguous_items=ambiguous,
            unrecognized_items=unrecognized,
            raw_input=raw_text
        )

    def _check_is_question(self, text: str, positions: List[CatalogPosition]) -> Tuple[bool, Optional[CatalogPosition]]:
        t_lower = text.lower()
        question_markers = ["сколько осталось", "какой остаток", "остаток по", "сколько еще осталось", "осталось ли"]
        if any(qm in t_lower for qm in question_markers):
            candidates = RuleMatcher.find_candidates(t_lower, positions)
            if candidates:
                return True, candidates[0][0]
            return True, None
        return False, None

    def _fallback_extract(self, text: str, positions: List[CatalogPosition]) -> ExtractionResult:
        logger.info("Использование встроенного интеллектуального парсера")
        t_lower = text.lower().replace("—", "-").replace("–", "-")

        matched: List[Dict[str, Any]] = []
        ambiguous: List[Dict[str, Any]] = []

        # Медь 6-ка
        m6 = re.search(r'(?:медь\s*)?(?:6[- ]?ку?|шест[её]рк[ау])\s*(\d+[\.,]?\d*)\s*(?:м|метр)?', t_lower)
        vol_6 = None
        if m6:
            vol_6 = float(m6.group(1).replace(",", "."))
            p6 = next((p for p in positions if "6,35" in p.name and "фреонопровод" in p.name.lower()), None)
            if p6:
                matched.append({"row_idx": p6.row_idx, "volume": vol_6, "unit": "м", "raw_text": m6.group(0)})

        # Медь 9-ка
        m9 = re.search(r'(?:медь\s*)?(?:9[- ]?ку?|девятк[ау])\s*(\d+[\.,]?\d*)\s*(?:м|метр)?', t_lower)
        vol_9 = None
        if m9:
            vol_9 = float(m9.group(1).replace(",", "."))
            p9 = next((p for p in positions if "9,52" in p.name and "фреонопровод" in p.name.lower()), None)
            if p9:
                matched.append({"row_idx": p9.row_idx, "volume": vol_9, "unit": "м", "raw_text": m9.group(0)})

        # Медь 12-ка (12-ю медь, двенашка)
        m12 = re.search(r'(?:(?:12[- ]?[яюе]?\s*медь|медь\s*12[- ]?[яюека]*|двенашк[ау])\s*(\d+[\.,]?\d*)\s*(?:м|метр\w*)?|(\d+[\.,]?\d*)\s*(?:м|метр\w*)?\s*(?:12[- ]?[яюе]?\s*медь|медь\s*12[- ]?[яюека]*|двенашк[ау]))', t_lower)
        if m12:
            vol_12_str = m12.group(1) or m12.group(2)
            if vol_12_str:
                vol_12 = float(vol_12_str.replace(",", "."))
                p12 = next((p for p in positions if ("12.7" in p.name or "12,7" in p.name) and "фреонопровод" in p.name.lower()), None)
                if p12:
                    matched.append({"row_idx": p12.row_idx, "volume": vol_12, "unit": "м", "raw_text": m12.group(0)})

        # Шпильки (шпилек М8 15 шт, 15 шпилек М8)
        m_shp = re.search(r'(?:(\d+[\.,]?\d*)\s*(?:шт|штук)?\s*шпилек\w*(?:\s*м8)?|шпилек\w*(?:\s*м8)?\s*(\d+[\.,]?\d*))', t_lower)
        if m_shp:
            vol_shp_str = m_shp.group(1) or m_shp.group(2)
            if vol_shp_str:
                vol_shp = float(vol_shp_str.replace(",", "."))
                p_shp = next((p for p in positions if "шпилька" in p.name.lower()), None)
                if p_shp:
                    matched.append({"row_idx": p_shp.row_idx, "volume": vol_shp, "unit": "шт", "raw_text": m_shp.group(0)})

        # Труба ПВХ (двадцатка 45 м, 20 мм 45 м)
        m_pvh = re.search(r'труб\w*\s*пвх\s*(?:двадцатк\w*|20\s*мм|20)[^\d]*(\d+[\.,]?\d*)\s*(?:м|метр\w*)?', t_lower)
        if m_pvh:
            vol_pvh = float(m_pvh.group(1).replace(",", "."))
            p_pvh = next((p for p in positions if "труба пвх" in p.name.lower() and "20" in p.name), None)
            if p_pvh:
                matched.append({"row_idx": p_pvh.row_idx, "volume": vol_pvh, "unit": "м", "raw_text": m_pvh.group(0)})

        # Автоматы на DIN-рейку (3 автомата на дин-рейку, 3 автомата)
        m_av = re.search(r'(\d+[\.,]?\d*)\s*(?:шт|штук)?\s*автомат\w*(?:\s*на\s*дин[- ]?рейку)?', t_lower)
        if m_av:
            vol_av = float(m_av.group(1).replace(",", "."))
            p_av = next((p for p in positions if "установка ав" in p.name.lower()), None) or next((p for p in positions if "дин-рейк" in p.name.lower()), None)
            if p_av:
                matched.append({"row_idx": p_av.row_idx, "volume": vol_av, "unit": "шт", "raw_text": m_av.group(0)})

        # Дренажные помпы (2 помпы зауерман, 2 помпы sauermann)
        m_pmp = re.search(r'(\d+[\.,]?\d*)\s*(?:шт|штук)?\s*(?:помп\w*|насос\w*)\s*(?:зауерман\w*|sauermann)', t_lower)
        if m_pmp:
            vol_pmp = float(m_pmp.group(1).replace(",", "."))
            p_pmp = next((p for p in positions if "sauermann" in p.name.lower() or "помпа" in p.name.lower()), None)
            if p_pmp:
                matched.append({"row_idx": p_pmp.row_idx, "volume": vol_pmp, "unit": "шт", "raw_text": m_pmp.group(0)})

        # Изоляция "столько же"
        if "изоляц" in t_lower:
            if "столько же" in t_lower or "так же" in t_lower:
                if vol_6 is not None:
                    p_iso6 = next((p for p in positions if "6,35" in p.name and "теплоизоляционная" in p.name.lower()), None)
                    if p_iso6:
                        matched.append({"row_idx": p_iso6.row_idx, "volume": vol_6, "unit": "м", "raw_text": f"изоляция на 6-ку {vol_6} м"})
                if vol_9 is not None:
                    p_iso9 = next((p for p in positions if "9,52" in p.name and "теплоизоляционная" in p.name.lower()), None)
                    if p_iso9:
                        matched.append({"row_idx": p_iso9.row_idx, "volume": vol_9, "unit": "м", "raw_text": f"изоляция на 9-ку {vol_9} м"})

        # Кабель 3х2,5
        cable_match = re.search(r'кабель[^\d]*(\d+)\s*[xх*]\s*([\d,\.]+)[^\d]*(\d+[\.,]?\d*)\s*(?:м|метр)?', t_lower)
        if cable_match:
            c_sec = f"{cable_match.group(1)}х{cable_match.group(2).replace('.', ',')}"
            c_vol = float(cable_match.group(3).replace(",", "."))
            p_cable = next((p for p in positions if "кабель силовой" in p.name.lower() and c_sec in p.name.lower()), None)
            if p_cable:
                matched.append({"row_idx": p_cable.row_idx, "volume": c_vol, "unit": "м", "raw_text": cable_match.group(0)})

        # Хомуты под фреон
        if "хомут" in t_lower:
            num_find = re.search(r'(\d+)\s*хомут|хомут\w*[^\d]*(\d+)', t_lower)
            vol_h = float(num_find.group(1) or num_find.group(2)) if num_find else 10.0
            if "фреон" in t_lower or "32" in t_lower:
                p_hf = next((p for p in positions if "хомут" in p.name.lower() and "фреон" in p.name.lower()), None)
                if p_hf:
                    matched.append({"row_idx": p_hf.row_idx, "volume": vol_h, "unit": "шт", "raw_text": f"{vol_h} хомутов под фреон"})
            elif "дренаж" in t_lower or "25" in t_lower:
                p_hd = next((p for p in positions if "хомут" in p.name.lower() and "дренаж" in p.name.lower()), None)
                if p_hd:
                    matched.append({"row_idx": p_hd.row_idx, "volume": vol_h, "unit": "шт", "raw_text": f"{vol_h} хомутов под дренаж"})
            else:
                h_cands = [p.row_idx for p in positions if "хомут" in p.name.lower()]
                ambiguous.append({
                    "raw_text": f"{vol_h} хомутов",
                    "volume": vol_h,
                    "unit": "шт",
                    "candidate_row_indices": h_cands,
                    "reason": "Уточните: хомут для дренажа (М8 25мм) или для фреонопровода (М8 32мм)?"
                })

        data = {
            "is_question": False,
            "matched_items": matched,
            "ambiguous_items": ambiguous,
            "unrecognized_items": []
        }
        return self._process_extracted_json(data, text, positions)
