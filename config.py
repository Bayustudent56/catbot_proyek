"""Konfigurasi CatBot. Nilai sensitif dibaca dari environment / file .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "ganti-dengan-secret-key-acak")

    # SQLite (default) atau MySQL, contoh:
    # DATABASE_URL=mysql+pymysql://user:password@localhost/catbot
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'catbot.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 30  # 30 hari

    TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "7"))  # WIB
    MAX_MESSAGE_LENGTH = 500
