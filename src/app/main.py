from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.services.parser import recover_stale_pending


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("应用启动中...")
    stale = recover_stale_pending()
    if stale:
        print(f"已将 {stale} 条超时未解析的简历标记为 failed，可在页面重新解析")
    yield
    print("应用关闭中...")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="JD Agent API",
        version=settings.VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def health():
        return {
            "status": "ok",
            "llm_configured": bool((settings.LLM_API_KEY or "").strip()),
            "llm_model": settings.LLM_MODEL,
            "llm_mock": settings.LLM_MOCK,
        }

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
