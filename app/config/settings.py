from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CampusOverflow"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://campus:campus@localhost:5432/campus"
    # 连接池参数。db_pool_size=0 是哨兵：表示继续用 NullPool（默认，测试/CI 零影响），
    # 绝不直接传入池——SQLAlchemy 语义下 pool_size=0 是"无上限池"（max_overflow 被强制为 -1）。
    # >0 时启用 AsyncAdaptedQueuePool，单进程连接上限 = db_pool_size + db_max_overflow。
    db_pool_size: int = 0
    db_max_overflow: int = 10
    db_pool_timeout: int = 10
    redis_url: str = "redis://localhost:6379/0"
    # JWT 签名密钥：默认仅开发用，生产必须从环境变量覆盖（.env 不入库）
    jwt_secret: str = "dev-secret-change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
