from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = Field(default="postgresql://stockbot:password@localhost:5432/stockbot")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # FinMind
    finmind_api_token: str = Field(default="")

    # LINE Messaging API
    line_channel_access_token: str = Field(default="")
    line_user_id: str = Field(default="")  # User ID or Group ID to push messages to

    # Telegram
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # Admin API Security
    admin_api_key: str = Field(default="change_this_to_a_secure_random_string")

    # Scoring Weights
    weight_technical: float = Field(default=0.35)
    weight_institutional: float = Field(default=0.35)
    weight_margin: float = Field(default=0.10)
    weight_macro: float = Field(default=0.20)

    # Polymarket slugs
    poly_fed_cut_slug: str = Field(default="will-the-fed-cut-rates-in-2025")
    poly_nvidia_beat_slug: str = Field(default="will-nvidia-beat-q1-2025-earnings")
    poly_taiwan_strait_slug: str = Field(default="taiwan-strait-incident-2025")
    poly_china_gdp_slug: str = Field(default="will-china-miss-gdp-target-2025")
    poly_oil_90_slug: str = Field(default="will-oil-be-above-90-end-of-2025")

    # App
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
