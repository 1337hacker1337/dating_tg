from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")

    # PostgreSQL
    db_dsn: str = Field(..., alias="DATABASE_URL")

    # Webhook (опционально)
    use_webhook: bool = Field(False, alias="USE_WEBHOOK")
    webhook_host: str = Field("", alias="WEBHOOK_HOST")
    webhook_path: str = Field("/webhook", alias="WEBHOOK_PATH")
    webhook_port: int = Field(8080, alias="WEBHOOK_PORT")

    # Admin panel
    admin_secret: str = Field("changeme", alias="ADMIN_SECRET")
    admin_port: int = Field(8000, alias="ADMIN_PORT")

    # Алгоритм подбора
    nearby_radius_km: int = Field(50, alias="NEARBY_RADIUS_KM")


settings = Settings()
