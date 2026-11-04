import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram
    TELEGRAM_BOT_TOKEN: str = "MOCK_BOT_TOKEN"

    # LLM Provider: "gemini" (по умолчанию, бесплатно) или "openai"
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # OpenAI (опционально)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "gpt-4o-mini"
    WHISPER_MODEL: str = "whisper-1"

    # Groq (опционально)
    GROQ_API_KEY: Optional[str] = None

    # Google Sheets
    GOOGLE_APPS_SCRIPT_URL: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = "service_account.json"
    GOOGLE_SPREADSHEET_ID: Optional[str] = None
    GOOGLE_WORKSHEET_NAME: str = "Лист1"
    GOOGLE_SHEET_URL: Optional[str] = None

    # Bitrix24
    BITRIX24_WEBHOOK_URL: Optional[str] = None
    BITRIX24_RESPONSIBLE_ID: int = 1
    BITRIX24_CREATE_TASK: bool = True
    BITRIX24_CREATE_FEED_POST: bool = True

    # Local fallback
    LOCAL_EXCEL_PATH: str = "Ежедневное_выполнение_Садик.xlsx"
    ALLOW_MOCK_FALLBACK: bool = True


settings = Settings()
