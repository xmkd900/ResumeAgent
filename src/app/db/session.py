from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

_url = make_url(settings.DATABASE_URL)
# 容器里的 MySQL 默认 UTC，而前端按本地时间展示 naive datetime。
# 统一连接时区为东八区，保证 NOW() 写入的时间与用户看到的一致。
_connect_args = {}
if _url.get_backend_name() == "mysql":
    _connect_args["init_command"] = "SET time_zone = '+08:00'"

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
