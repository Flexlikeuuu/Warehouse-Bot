import datetime
import logging
import asyncio
from typing import List, Optional, Tuple, Dict, Any
import aiohttp

from config.settings import settings
from models.schemas import ReportItem

logger = logging.getLogger(__name__)


class Bitrix24Service:
    """Сервис интеграции с Битрикс24 через REST API (входящий вебхук)."""

    def __init__(self):
        self.webhook_url = settings.BITRIX24_WEBHOOK_URL
        self.responsible_id = settings.BITRIX24_RESPONSIBLE_ID
        self.create_task_enabled = settings.BITRIX24_CREATE_TASK
        self.create_feed_post_enabled = settings.BITRIX24_CREATE_FEED_POST

    def is_configured(self) -> bool:
        return bool(
            self.webhook_url 
            and "your-portal" not in self.webhook_url 
            and self.webhook_url.startswith("http")
        )

    def _normalize_url(self, method: str) -> str:
        url = self.webhook_url.rstrip("/")
        if not url.endswith(method):
            url = f"{url}/{method}"
        return url

    async def verify_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "Вебхук Битрикс24 не настроен в .env"

        try:
            url = self._normalize_url("server.time.json")
            # Быстрый таймаут 2.5 секунды, чтобы скрипт не висел
            timeout = aiohttp.ClientTimeout(total=2.5, connect=2.0)
            headers = {"User-Agent": "Mozilla/5.0"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if resp.status == 200 and "result" in data:
                        return True, f"Соединение успешно (время сервера: {data.get('result')})"
                    return False, f"Ответ Битрикс24: {data}"
        except Exception:
            return False, "Таймаут сети (отключите VPN, если включен)"

    async def send_report(
        self, 
        items: List[ReportItem], 
        date_target: Optional[datetime.date] = None, 
        master_name: str = "Мастер",
        sheet_url: Optional[str] = None
    ) -> Dict[str, Any]:
        target_date = date_target or datetime.date.today()
        date_str = target_date.strftime("%d.%m.%Y")

        if not self.is_configured():
            logger.info("Битрикс24 не настроен. Работает в режиме симуляции.")
            return {
                "success": True,
                "simulated": True,
                "message": "Симуляция отправки в Битрикс24 (вебхук не указан)",
                "task_id": 9999,
                "task_url": "https://bitrix24.example.com/company/personal/user/1/tasks/task/view/9999/"
            }

        result = {
            "success": False,
            "task_id": None,
            "task_url": None,
            "post_id": None,
            "errors": []
        }

        total_salary = 0.0
        lines = []
        for i, it in enumerate(items, 1):
            earned = it.volume * it.position.price_per_unit
            total_salary += earned
            warn = f" [⚠️ ПРЕВЫШЕНИЕ ОСТАТКА НА {it.over_limit_amount} {it.unit}]" if it.is_over_limit else ""
            lines.append(
                f"{i}. {it.position.name}\n"
                f"   • Выполнено: {it.volume} {it.unit} (ЗП за ед: {it.position.price_per_unit} руб. = {earned:.2f} руб.){warn}"
            )

        items_text = "\n".join(lines)
        sheet_ref = f"\n\n📊 Ссылка на Google Таблицу: {sheet_url}" if sheet_url else ""

        # 1. Создание Задачи в Битрикс24
        if self.create_task_enabled:
            task_title = f"🏗 Дневной отчёт за {date_str} — {master_name}"
            task_desc = (
                f"Ежедневный отчет мастера ({master_name}) о выполненных работах за {date_str}.\n\n"
                f"Выполненные объемы:\n{items_text}\n\n"
                f"Итого ЗП за день: {total_salary:.2f} руб."
                f"{sheet_ref}"
            )

            task_payload = {
                "fields": {
                    "TITLE": task_title,
                    "DESCRIPTION": task_desc,
                    "RESPONSIBLE_ID": self.responsible_id,
                    "DEADLINE": datetime.datetime.combine(target_date, datetime.time(23, 59)).strftime("%Y-%m-%d %H:%M:%S"),
                    "TAGS": ["Строительство", "Отчет", "ОВ3", "ЭМ3"]
                }
            }

            try:
                url = self._normalize_url("tasks.task.add.json")
                timeout = aiohttp.ClientTimeout(total=3.0, connect=2.0)
                headers = {"User-Agent": "Mozilla/5.0"}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.post(url, json=task_payload) as resp:
                        res_data = await resp.json()
                        if resp.status == 200 and "result" in res_data:
                            task_info = res_data["result"].get("task", {})
                            task_id = task_info.get("id") or res_data["result"]
                            result["task_id"] = task_id
                            portal_base = self.webhook_url.split("/rest/")[0]
                            result["task_url"] = f"{portal_base}/company/personal/user/{self.responsible_id}/tasks/task/view/{task_id}/"
                            result["success"] = True
                            logger.info(f"Задача #{task_id} успешно создана в Битрикс24")
            except Exception as e:
                logger.warning(f"Битрикс24 (задача): {e}")
                result["errors"].append(str(e))

        # 2. Публикация в Живую Ленту
        if self.create_feed_post_enabled:
            post_title = f"Отчёт прораба за {date_str}"
            post_message = (
                f"[B]Отчёт о выполненных работах за {date_str}[/B]\n"
                f"Мастер: {master_name}\n\n"
                f"{items_text}\n\n"
                f"[B]Итого начислено:[/B] {total_salary:.2f} руб."
                f"{sheet_ref}"
            )

            feed_payload = {
                "POST_TITLE": post_title,
                "POST_MESSAGE": post_message,
                "DEST": ["UA"]
            }

            try:
                url = self._normalize_url("log.blogpost.add.json")
                timeout = aiohttp.ClientTimeout(total=3.0, connect=2.0)
                headers = {"User-Agent": "Mozilla/5.0"}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.post(url, json=feed_payload) as resp:
                        res_data = await resp.json()
                        if resp.status == 200 and "result" in res_data:
                            result["post_id"] = res_data["result"]
                            result["success"] = True
                            logger.info(f"Пост в ленту #{res_data['result']} опубликован в Битрикс24")
            except Exception as e:
                logger.warning(f"Битрикс24 (лента): {e}")

        return result
