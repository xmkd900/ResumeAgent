from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.session import engine
from app.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时的操作
    print("应用启动中...")
    try:
        # v0 便捷建表；P0 引入 alembic 后改由迁移管理
        Base.metadata.create_all(bind=engine)
        print("数据库表已就绪")
    except Exception as e:  # noqa: BLE001  启动期允许任何建表失败：告警而非崩溃
        print(f"数据库未就绪（先 docker compose up -d mysql）：{e}")
    yield
    # 关闭时的操作
    print("应用关闭中...")


def create_app() -> FastAPI:
    """创建FastAPI应用实例"""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="JD Agent API",
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
