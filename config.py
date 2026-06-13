from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(..., alias="BOT_TOKEN")
    db_dsn: str = Field(..., alias="DATABASE_URL")

    use_webhook: bool = Field(False, alias="USE_WEBHOOK")
    webhook_host: str = Field("", alias="WEBHOOK_HOST")
    webhook_path: str = Field("/webhook", alias="WEBHOOK_PATH")
    webhook_port: int = Field(8080, alias="WEBHOOK_PORT")

    admin_secret: str = Field("changeme", alias="ADMIN_SECRET")
    admin_port: int = Field(8000, alias="ADMIN_PORT")

    nearby_radius_km: int = Field(50, alias="NEARBY_RADIUS_KM")

    # Свой постоянный канал для обязательной подписки.
    # Формат: @username или -100xxxxxxxxxx. Пусто — не проверяется.
    own_channel_id: Optional[str] = Field(None, alias="OWN_CHANNEL_ID")

    # Telegram ID первого администратора — добавляется автоматически при старте.
    first_admin_id: Optional[int] = Field(None, alias="FIRST_ADMIN_ID")


settings = Settings()
