from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 应用
    PROJECT_NAME: str = "JDAgent"
    VERSION: str = "0.1.0"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]  # Vue3 dev server

    DATABASE_URL: str = "mysql+pymysql://root:123456@localhost:3307/jdagent?charset=utf8mb4"

    # JWT
    SECRET_KEY: str = "dev-secret-change-me"  # 生产环境必须换随机长密钥
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天


settings = Settings()
