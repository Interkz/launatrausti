"""
Application configuration loaded from environment variables.

Uses python-dotenv to load .env files in development.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root (no-op if missing)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "launatrausti.db")

# Security
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

# Debug mode
DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# CORS origins (comma-separated)
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
