"""App settings, read from .env / environment (techstack section 14)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": .env also holds VITE_* vars we don't read here.
    # protected_namespaces=(): pydantic reserves "model_", and we have model_dir.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    # Host is "db" inside Compose. Use localhost only when running Python outside Docker.
    database_url: str = "postgresql+psycopg://pipeguard:pipeguard@db:5432/pipeguard"

    # ElevenLabs. Server-side only, never sent to the browser.
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    elevenlabs_webhook_secret: str = ""
    elevenlabs_environment: str = ""  # "backup" for the laptop failover

    # Auth for tool endpoints and admin/test-mode endpoints.
    voice_tool_secret: str = ""
    admin_token: str = ""

    public_base_url: str = "https://pipeguard.blunelabs.com"
    domain: str = "pipeguard.blunelabs.com"

    # Paths inside the containers.
    model_dir: str = "/app/ml/artifacts"
    scenario_path: str = "/app/infra/scenario.json"

    # Illustrative cost assumptions (stated openly in the pitch).
    cost_breakdown: float = 200_000
    cost_service: float = 20_000
    cost_instrument_check: float = 1_000

    # Alert rules (techstack 7.8).
    horizon_days: int = 14
    confirm_readings: int = 3
    max_calls_per_tech_per_day: int = 3
    ring_seconds: int = 30          # real seconds before a ring counts as missed
    webhook_pull_seconds: int = 60  # wait this long for the webhook, then pull

    # MOCK_API=1 serves api/fixtures/*.json instead of real data.
    mock_api: bool = False


@lru_cache
def get_settings() -> Settings:
    # Cached so every module shares one parsed copy.
    return Settings()
