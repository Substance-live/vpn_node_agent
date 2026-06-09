from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Security
    AGENT_SECRET: str = "changeme"

    # 3x-ui
    XUI_BASE_URL: str = "http://127.0.0.1:2053"
    XUI_USERNAME: str = "changeme"
    XUI_PASSWORD: str = "changeme"
    XUI_VLESS_INBOUND_ID: int = 1

    # MTProto (mtg)
    MTG_CONFIG_PATH: str = "/etc/mtg/config.toml"
    MTG_SERVER_IP: str = "127.0.0.1"
    MTG_PORT: int = 2443

    # Server
    PORT: int = 8080

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" for prod, "console" for dev


settings = Settings()
