from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "user"
    __table_args__ = ({"comment": "用户账号：登录与数据归属"},)

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="用户 ID，自增主键"
    )
    username: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, comment="登录名，全局唯一"
    )
    password_hash: Mapped[str] = mapped_column(
        String(100), comment="bcrypt 密码哈希，不存明文"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="注册时间"
    )
