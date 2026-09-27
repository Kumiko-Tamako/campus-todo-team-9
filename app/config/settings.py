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
    # asyncpg 建连超时（秒）：驱动默认 60s，PG"黑洞"（不拒连）时请求会挂满 60s，
    # 5s 快速失败转 503（第六路观察点闭环）
    db_connect_timeout: int = 5
    # 服务端语句/锁等待超时（毫秒，经 server_settings 下发）：防外部行锁令写请求
    # 无上限挂起、NullPool 下堆积连接（第八路观察点 2）；超时错误（55P03/57014）
    # 经分层落 503 可重试
    db_statement_timeout_ms: int = 5000
    db_lock_timeout_ms: int = 5000
    redis_url: str = "redis://localhost:6379/0"
    # JWT 签名密钥：默认仅开发用，生产必须从环境变量覆盖（.env 不入库）
    jwt_secret: str = "dev-secret-change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
