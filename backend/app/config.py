import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_TITLE: str = "SmartDev AI IoT Engine & Tasmota Adapter"
    APP_DESCRIPTION: str = "Intelligent IoT Hub featuring Llama AI Copilot, Predictive Telemetry Diagnostics, Automations & Tasmota MQTT Adapter"
    APP_VERSION: str = "2.0.0"

    # MQTT Broker Configuration
    MQTT_HOST: str = os.getenv("MQTT_HOST", "127.0.0.1")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_KEEPALIVE: int = 60
    MQTT_USERNAME: str | None = os.getenv("MQTT_USERNAME", None)
    MQTT_PASSWORD: str | None = os.getenv("MQTT_PASSWORD", None)

    # Device defaults (Physical hardware)
    DEFAULT_DEVICE_ID: str = os.getenv("DEFAULT_DEVICE_ID", "tasmota_0C3249")

    # API Server Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # CORS settings (allows mobile and web apps)
    CORS_ORIGINS: list[str] = ["*"]

    # Security / API Key Authentication
    API_KEY: str = os.getenv("API_KEY", "udit")
    API_KEY_HEADER: str = "X-API-Key"

    # AI Configuration (Llama / Ollama / Groq / Fallback)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "auto")  # 'auto', 'ollama', 'groq', 'builtin'
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


settings = Settings()
