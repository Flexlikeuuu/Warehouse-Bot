import sys
import os
import openpyxl

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import settings
from services.sheets_service import GoogleSheetsService


def main():
    print("=" * 60)
    print(" 📤 ЭКСПОРТ ШАБЛОНА В GOOGLE SHEETS")
    print("=" * 60)

    sheets = GoogleSheetsService()
    if not sheets.is_configured():
        print(
            "\n💡 Как создать Google Таблицу из файла за 1 минуту:\n\n"
            "1. Откройте Google Диск: https://drive.google.com\n"
            "2. Перетащите файл 'Ежедневное_выполнение_Садик.xlsx' в Google Диск.\n"
            "3. Дважды кликните по загруженному файлу и нажмите 'Открыть с помощью Google Таблицы'.\n"
            "4. В меню выберите: 'Файл' -> 'Сохранить как Google Таблицу'.\n"
            "5. Скопируйте ID таблицы из адресной строки браузера:\n"
            "   https://docs.google.com/spreadsheets/d/<ВОТ_ЭТОТ_ID>/edit\n"
            "6. Нажмите 'Поделиться' -> Добавьте email сервисного аккаунта Google (из service_account.json) с правами 'Редактор' (Editor).\n"
            "7. Укажите ID и URL в файле .env (GOOGLE_SPREADSHEET_ID и GOOGLE_SHEET_URL).\n"
        )
        return

    print(f"Подключение к таблице ID: {sheets.spreadsheet_id}...")
    try:
        ws = sheets._get_worksheet()
        print(f"✅ Успешное подключение! Лист: {ws.title}")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")


if __name__ == "__main__":
    main()

