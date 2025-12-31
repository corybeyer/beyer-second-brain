"""Shared configuration for Second Brain."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
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
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "books")

# PostgreSQL
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "secondbrain")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Anthropic (optional)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
