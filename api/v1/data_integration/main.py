"""Data Integration API만 실행하는 진입점.

backend/api/v1/data_integration 라우터만 올려 한 포트에서 서비스합니다.
전체 Backend API는 backend/api/v1/main.py 를 사용하세요.

MCP SR Index 도구 서버: MCP_SR_INDEX_TOOLS_URL이 미설정이면 main 기동 시 자동으로
서브프로세스로 기동합니다. 이미 URL이 설정되어 있으면 별도 서버를 사용합니다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# 프로젝트 루트(ifrsseedr_re)를 path에 추가 — import backend 사용을 위해
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from dotenv import load_dotenv
    # 셸에 남아 있는 이전 환경변수보다 .env 값을 우선 적용
    load_dotenv(_project_root / ".env", override=True)
except ImportError:
    pass

from fastapi import FastAPI

from backend.api.v1.data_integration.routes import router as data_integration_router
from backend.core.config.settings import get_settings


def _mcp_index_bind() -> tuple[str, int, str]:
    """자동 기동 MCP 바인딩: MCP_SR_INDEX_TOOLS_* 우선, 없으면 공통 MCP_HTTP_* (core settings)."""
    s = get_settings()
    host = os.environ.get("MCP_SR_INDEX_TOOLS_HOST", "").strip() or s.mcp_http_host
    port_s = os.environ.get("MCP_SR_INDEX_TOOLS_PORT", "").strip()
    port = int(port_s) if port_s else s.mcp_http_port
    path = os.environ.get("MCP_SR_INDEX_TOOLS_PATH", "").strip() or s.mcp_http_path
    return host, port, path

# 자동 기동한 MCP Index 서버 프로세스 (shutdown 시 종료용)
_mcp_index_server_process: subprocess.Popen | None = None

# MCP Index 서버 스크립트 경로 (프로젝트 루트 기준)
_MCP_INDEX_SERVER_SCRIPT = (
    _project_root / "backend" / "domain" / "v1" / "data_integration"
    / "spokes" / "infra" / "sr_index_tools_server.py"
)


def _wait_for_port(host: str, port: int, timeout_sec: float = 30.0, interval: float = 0.3) -> bool:
    """지정 포트가 열릴 때까지 대기."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (OSError, socket.error):
            time.sleep(interval)
    return False


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """앱 수명 주기: MCP Index 서버 자동 기동/종료."""
    global _mcp_index_server_process

    url_raw = os.environ.get("MCP_SR_INDEX_TOOLS_URL", "").strip()
    if url_raw:
        # 사용자 정보/쿼리스트링 노출 방지를 위해 간단 마스킹
        masked_url = url_raw.split("?", 1)[0]
    else:
        masked_url = "(unset)"

    # 런타임 환경 확인용 시작 로그 (민감정보는 값 대신 설정 여부만 출력)
    llama_set = bool(get_settings().llama_cloud_api_key.strip())
    print(
        "[DataIntegration] env check: "
        f"MCP_SR_INDEX_TOOLS_URL={'set' if url_raw else 'unset'}({masked_url}), "
        f"LLAMA_CLOUD_API_KEY={'set' if llama_set else 'unset'}",
        file=sys.stderr,
        flush=True,
    )

    url_env = url_raw
    if url_env:
        # 이미 URL이 설정됨 → 별도 서버 사용, 자동 기동 안 함
        yield
        return

    # 자동 기동: 서브프로세스로 sr_index_tools_server.py 실행 (Streamable HTTP)
    mcp_host, mcp_port, mcp_path = _mcp_index_bind()
    url = f"http://{mcp_host}:{mcp_port}{mcp_path}"

    if not _MCP_INDEX_SERVER_SCRIPT.exists():
        # 스크립트 없으면 자동 기동 스킵 (stdio 등 다른 방식 사용 시)
        yield
        return

    env = os.environ.copy()
    env["MCP_HTTP"] = "1"
    env["MCP_HTTP_HOST"] = mcp_host
    env["MCP_HTTP_PORT"] = str(mcp_port)
    env["MCP_HTTP_PATH"] = mcp_path

    try:
        _mcp_index_server_process = subprocess.Popen(
            [sys.executable, str(_MCP_INDEX_SERVER_SCRIPT)],
            cwd=str(_project_root),
            env=env,
            stdout=subprocess.DEVNULL,
            # PIPE를 사용하면 부모가 읽지 않을 때 버퍼 포화로 멈출 수 있어 상속 출력 사용
            stderr=None,
        )
        # 클라이언트가 이 URL로 연결하도록 설정
        os.environ["MCP_SR_INDEX_TOOLS_URL"] = url

        if _wait_for_port(mcp_host, mcp_port, timeout_sec=25.0):
            print(f"[DataIntegration] MCP SR Index 도구 서버 자동 기동: {url}", file=sys.stderr, flush=True)
        # 대기 실패해도 URL은 설정됨 → 첫 요청 시 재시도 등으로 동작 가능

        yield
    finally:
        if _mcp_index_server_process is not None:
            try:
                _mcp_index_server_process.terminate()
                _mcp_index_server_process.wait(timeout=5)
            except Exception:
                try:
                    _mcp_index_server_process.kill()
                except Exception:
                    pass
            _mcp_index_server_process = None
        if os.environ.get("MCP_SR_INDEX_TOOLS_URL") == url:
            os.environ.pop("MCP_SR_INDEX_TOOLS_URL", None)


app = FastAPI(
    title="Data Integration API",
    description="에이전트 기반 지속가능경영보고서(SR) 검색·다운로드 API",
    version="0.1.0",
    lifespan=_lifespan,
)
app.include_router(data_integration_router)


def run(host: str = "0.0.0.0", port: int | None = None) -> None:
    """ASGI 앱을 실행합니다."""
    import uvicorn

    if port is None:
        port = get_settings().data_integration_port
    reload = get_settings().data_integration_reload
    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
