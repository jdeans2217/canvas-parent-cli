#!/usr/bin/env python3
"""
Configuration Module - Centralized configuration for Canvas Parent CLI

Loads and validates all configuration from environment variables.
"""

import os
from typing import Optional, List
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CanvasConfig:
    """Canvas API configuration."""
    api_url: str = ""
    api_key: str = ""

    def is_valid(self) -> bool:
        return bool(self.api_url and self.api_key)


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration."""
    url: str = ""

    def is_valid(self) -> bool:
        return bool(self.url)


@dataclass
class EmailConfig:
    """Email/Gmail configuration."""
    recipients: List[str] = field(default_factory=list)
    schedule: str = "daily"  # daily, weekly, or both
    time: str = "07:00"
    grade_alert_threshold: int = 80
    credentials_file: str = "credentials.json"

    def is_valid(self) -> bool:
        return bool(self.recipients)


@dataclass
class CalendarConfig:
    """Google Calendar configuration."""
    enabled: bool = False
    student_calendars: dict = field(default_factory=dict)  # student_id -> calendar_id
    color_by: str = "course"  # course or urgency


@dataclass
class LLMConfig:
    """LLM provider configuration (provider-agnostic)."""
    provider: str = "ollama"  # ollama, openai, gemini, or claude

    # Ollama
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.2:latest"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-pro"

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-sonnet-20240229"

    def get_provider_config(self) -> dict:
        """Get configuration for the selected provider."""
        if self.provider == "ollama":
            return {"url": self.ollama_url, "model": self.ollama_model}
        elif self.provider == "openai":
            return {"api_key": self.openai_api_key, "model": self.openai_model}
        elif self.provider == "gemini":
            return {"api_key": self.gemini_api_key, "model": self.gemini_model}
        elif self.provider == "claude":
            return {"api_key": self.anthropic_api_key, "model": self.claude_model}
        return {}

    def is_valid(self) -> bool:
        if self.provider == "ollama":
            return bool(self.ollama_url)
        elif self.provider == "openai":
            return bool(self.openai_api_key)
        elif self.provider == "gemini":
            return bool(self.gemini_api_key)
        elif self.provider == "claude":
            return bool(self.anthropic_api_key)
        return False


@dataclass
class ScannerConfig:
    """Document scanning configuration."""
    watch_folder: str = ""
    ocr_provider: str = "mistral"  # mistral, tesseract, or google_vision
    mistral_api_key: str = ""
    google_vision_credentials: str = ""

    def is_valid(self) -> bool:
        if self.ocr_provider == "mistral":
            return bool(self.mistral_api_key)
        elif self.ocr_provider == "google_vision":
            return bool(self.google_vision_credentials)
        return True  # tesseract doesn't need credentials


@dataclass
class Config:
    """Main configuration container."""
    canvas: CanvasConfig = field(default_factory=CanvasConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)


def load_config() -> Config:
    """
    Load configuration from environment variables.

    Returns:
        Config object with all settings
    """
    config = Config()

    # Canvas
    config.canvas.api_url = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
    config.canvas.api_key = os.getenv("CANVAS_API_KEY", "")

    # Database
    config.database.url = os.getenv("DATABASE_URL", "")

    # Email
    recipients_str = os.getenv("EMAIL_RECIPIENTS", "")
    config.email.recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
    config.email.schedule = os.getenv("REPORT_SCHEDULE", "daily")
    config.email.time = os.getenv("REPORT_TIME", "07:00")
    config.email.grade_alert_threshold = int(os.getenv("GRADE_ALERT_THRESHOLD", "80"))
    config.email.credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    # Calendar
    config.calendar.enabled = os.getenv("CALENDAR_SYNC_ENABLED", "false").lower() == "true"
    config.calendar.color_by = os.getenv("CALENDAR_COLOR_BY", "course")

    # Load per-student calendar IDs (format: CALENDAR_STUDENT_{id}_ID)
    for key, value in os.environ.items():
        if key.startswith("CALENDAR_STUDENT_") and key.endswith("_ID"):
            student_key = key.replace("CALENDAR_STUDENT_", "").replace("_ID", "")
            config.calendar.student_calendars[student_key] = value

    # LLM
    config.llm.provider = os.getenv("LLM_PROVIDER", "ollama")
    config.llm.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    config.llm.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    config.llm.openai_api_key = os.getenv("OPENAI_API_KEY", "")
    config.llm.openai_model = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
    config.llm.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    config.llm.gemini_model = os.getenv("GEMINI_MODEL", "gemini-pro")
    config.llm.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    config.llm.claude_model = os.getenv("CLAUDE_MODEL", "claude-3-sonnet-20240229")

    # Scanner
    config.scanner.watch_folder = os.getenv("SCAN_WATCH_FOLDER", "")
    config.scanner.ocr_provider = os.getenv("OCR_PROVIDER", "mistral")
    config.scanner.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")
    config.scanner.google_vision_credentials = os.getenv("GOOGLE_VISION_CREDENTIALS", "")

    return config


def validate_config(config: Config) -> List[str]:
    """
    Validate configuration and return list of errors.

    Args:
        config: Config object to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not config.canvas.is_valid():
        errors.append("Canvas API not configured (CANVAS_API_URL and CANVAS_API_KEY required)")

    return errors


def print_config_status(config: Config):
    """Print configuration status for debugging."""
    print("Configuration Status")
    print("=" * 50)

    # Canvas
    print(f"\nCanvas API:")
    print(f"  URL: {config.canvas.api_url}")
    print(f"  Key: {'*' * 20}..." if config.canvas.api_key else "  Key: NOT SET")
    print(f"  Status: {'OK' if config.canvas.is_valid() else 'MISSING'}")

    # Database
    print(f"\nDatabase:")
    print(f"  URL: {config.database.url[:30]}..." if config.database.url else "  URL: NOT SET")
    print(f"  Status: {'OK' if config.database.is_valid() else 'NOT CONFIGURED'}")

    # Email
    print(f"\nEmail:")
    print(f"  Recipients: {', '.join(config.email.recipients) if config.email.recipients else 'NONE'}")
    print(f"  Schedule: {config.email.schedule}")
    print(f"  Time: {config.email.time}")
    print(f"  Status: {'OK' if config.email.is_valid() else 'NOT CONFIGURED'}")

    # Calendar
    print(f"\nCalendar:")
    print(f"  Enabled: {config.calendar.enabled}")
    print(f"  Student Calendars: {len(config.calendar.student_calendars)}")

    # LLM
    print(f"\nLLM Provider:")
    print(f"  Provider: {config.llm.provider}")
    print(f"  Status: {'OK' if config.llm.is_valid() else 'NOT CONFIGURED'}")

    # Scanner
    print(f"\nDocument Scanner:")
    print(f"  Watch Folder: {config.scanner.watch_folder or 'NOT SET'}")
    print(f"  OCR Provider: {config.scanner.ocr_provider}")
    if config.scanner.ocr_provider == "mistral":
        print(f"  Mistral API Key: {'*' * 20}..." if config.scanner.mistral_api_key else "  Mistral API Key: NOT SET")
    print(f"  Status: {'OK' if config.scanner.is_valid() else 'NOT CONFIGURED'}")


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        Config object (loaded on first call)
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    config = get_config()
    print_config_status(config)

    errors = validate_config(config)
    if errors:
        print("\nConfiguration Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\nConfiguration is valid!")
