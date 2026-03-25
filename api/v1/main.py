"""Backend API 진입점 — backend/api 라우터를 한 포트에서 실행합니다."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가 (.env 및 backend 패키지 사용)
_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(_project_root / ".env")
except ImportError:
    pass

from fastapi import FastAPI

from backend.api.v1.data_integration.routes import router as data_integration_router
from backend.api.v1.esg_data.routes import router as esg_data_router

app = FastAPI(
    title="Backend API",
    description="통합 Backend API (Data Integration 등)",
    version="0.1.0",
)

app.include_router(data_integration_router)
app.include_router(esg_data_router)


def run(host: str = "0.0.0.0", port: int = 9001) -> None:
    """ASGI 앱을 실행합니다."""
    import uvicorn
    reload = os.getenv("BACKEND_API_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "9001"))
    run(port=port)
