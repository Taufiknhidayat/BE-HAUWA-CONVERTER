"""Konfigurasi aplikasi, dibaca dari environment / file .env."""
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    odoo_url: str
    odoo_db: str
    odoo_api_key: str
    odoo_mock: bool
    max_upload_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    url = os.getenv('ODOO_URL', '').rstrip('/')
    db = os.getenv('ODOO_DB', '')
    key = os.getenv('ODOO_API_KEY', '')
    forced = os.getenv('ODOO_MOCK', '').lower() in ('1', 'true', 'yes')
    # Mode demo aktif kalau dipaksa, atau kalau URL / API key belum diisi.
    return Settings(url, db, key, forced or not (url and key))
