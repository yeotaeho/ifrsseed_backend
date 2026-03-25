"""data_integration 서비스 진입점. Python으로만 실행: python main.py"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트의 .env 로드 (DART_API_KEY 등)
_root = Path(__file__).resolve().parent.parent.parent
_project_root = _root.parent.parent  # backend/domain/v1 -> ifrsseedr_re
try:
    from dotenv import load_dotenv
    load_dotenv(_project_root / ".env")
except ImportError:
    pass

# python main.py 로 실행할 때 프로젝트 루트를 path에 추가 (backend.api 임포트용)
if __name__ == "__main__":
    if _project_root not in (Path(p).resolve() for p in sys.path):
        sys.path.insert(0, str(_project_root))

from fastapi import FastAPI

from backend.core.config.settings import get_settings

# API 레이어 라우터 사용 (레이어 구분: HTTP는 API에 두고, domain은 서비스만)
from backend.api.v1.data_integration.sr_agent_router import sr_agent_router

app = FastAPI(
    title="Data Integration API",
    description="에이전트 기반 지속가능경영보고서(SR) 검색·다운로드 API",
    version="0.1.0",
)
app.include_router(sr_agent_router)


def run(host: str = "0.0.0.0", port: int | None = None) -> None:
    """ASGI 앱을 실행합니다. python main.py 시 호출됩니다."""
    import uvicorn

    listen = port if port is not None else get_settings().data_integration_port
    uvicorn.run(
        app,
        host=host,
        port=listen,
        reload=get_settings().data_integration_reload,
    )


if __name__ == "__main__":
    run()
