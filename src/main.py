"""启动入口：uv run uvicorn app.main:app --reload（项目根目录执行）。"""

import uvicorn

from app.main import app  # noqa: F401  供 uvicorn main:app 兼容引用


def main():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
