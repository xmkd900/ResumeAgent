from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 无论从仓库根目录还是 src/ 启动，都读取同一份根目录 .env
BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    PROJECT_NAME: str = "JDAgent"
    VERSION: str = "0.1.0"
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    DATABASE_URL: str = "mysql+pymysql://root:123456@localhost:3307/jdagent?charset=utf8mb4"

    # JWT
    SECRET_KEY: str = "dev-secret-change-me"  # 生产环境必须换随机长密钥
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天
    UPLOAD_DIR: str = str(BASE_DIR / "src" / "uploads")
    MAX_UPLOAD_MB: int = 10

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"
    LLM_MOCK: bool = False  # 无 key 时自动使用启发式诊断
    LLM_TIMEOUT_SECONDS: int = 60
    DIAGNOSIS_PROMPT_VERSION: str = "diagnosis-v1"


settings = Settings()
