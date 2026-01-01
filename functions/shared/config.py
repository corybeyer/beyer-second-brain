"""Shared configuration for Second Brain."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
FUNCTIONS_DIR = PROJECT_ROOT / "functions"
APP_DIR = PROJECT_ROOT / "app"
SHARED_DIR = PROJECT_ROOT / "shared"


def get_env(key: str, default: str | None = None) -> str:
    """Get environment variable or raise if required and missing."""
    value = os.environ.get(key, default)
    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


# Azure Storage
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "documents")

# Azure SQL Database
AZURE_SQL_SERVER = os.environ.get("AZURE_SQL_SERVER", "")
AZURE_SQL_DATABASE = os.environ.get("AZURE_SQL_DATABASE", "secondbrain")
AZURE_SQL_USERNAME = os.environ.get("AZURE_SQL_USERNAME", "")
AZURE_SQL_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")
AZURE_SQL_USE_MI = os.environ.get("AZURE_SQL_USE_MI", "false")  # Use managed identity

# Anthropic Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
