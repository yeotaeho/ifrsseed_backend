"""SR 인덱스 에이전트용 FastMCP Tool Server.

get_pdf_metadata, inspect_index_pages, parse_index_with_docling, parse_index_with_llamaparse,
validate_index_rows, detect_anomalies, correct_anomalous_rows_with_md.
저장(save_sr_report_index_batch)은 오케스트레이터/API에서 수행 (B안).
"""
import asyncio
import json
import os
import sys
from pathlib import Path
try:
    from .path_resolver import find_repo_root
except ImportError:
    from path_resolver import find_repo_root

# 저장소 루트 (환경 변수/마커 파일 기반 탐색)
_repo_root = find_repo_root(Path(__file__))
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# .env 로드: 여러 경로 시도, override=True로 기존(빈) env 덮어쓰기
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    candidates = [
        _repo_root / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=True)
            break

_load_env()

from backend.core.config.settings import get_settings

# LlamaParse 사용 가능 여부 시작 시 한 번 로그 (키 값 노출 없음)
_llama_key_set = bool(get_settings().llama_cloud_api_key.strip())
print(
    f"[MCP] LLAMA_CLOUD_API_KEY {'설정됨' if _llama_key_set else '미설정 (LlamaParse 비사용)'}",
    file=sys.stderr,
    flush=True,
)

try:
    from fastmcp import FastMCP
except ImportError:
    print("Streamable HTTP 사용 시 pip install fastmcp 필요", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("SR Index Tools Server")


@mcp.tool()
async def get_pdf_metadata_tool(report_id: str) -> str:
    """DB에서 report 메타데이터(total_pages, index_page_numbers, report_name, report_year) 조회."""
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import get_pdf_metadata
    result = await asyncio.to_thread(get_pdf_metadata, report_id)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def inspect_index_pages_tool(pdf_bytes_b64: str, index_page_numbers: list) -> str:
    """인덱스 페이지별 복잡도·표 개수 파악 (Docling 사용 여부 판단용)."""
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import inspect_index_pages
    result = await asyncio.to_thread(inspect_index_pages, pdf_bytes_b64, index_page_numbers)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def parse_index_with_docling_tool(pdf_bytes_b64: str, report_id: str, pages: list) -> str:
    """Docling으로 지정 페이지 인덱스 표 파싱. 반환 sr_report_index를 validate/detect/save에 전달."""
    import time
    t0 = time.perf_counter()
    # Docling에 넘어온 파싱 페이지를 로그에 명시
    print(f"[MCP] parse_index_with_docling_tool 요청 파싱 페이지: {pages}", file=sys.stderr, flush=True)
    print(f"[MCP:DEBUG] parse_index_with_docling_tool 시작 report_id={report_id} pages={pages} pdf_b64_len={len(pdf_bytes_b64 or '')}", file=sys.stderr, flush=True)
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import parse_index_with_docling
    result = await asyncio.to_thread(parse_index_with_docling, pdf_bytes_b64, report_id, pages)
    elapsed = time.perf_counter() - t0
    idx_count = len(result.get("sr_report_index") or []) if isinstance(result, dict) else 0
    print(f"[MCP:DEBUG] parse_index_with_docling_tool 완료 {elapsed:.1f}s sr_report_index={idx_count}건", file=sys.stderr, flush=True)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def parse_index_with_llamaparse_tool(pdf_bytes_b64: str, pages: list) -> str:
    """LlamaParse로 지정 페이지 파싱 → 페이지별 마크다운 반환."""
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import parse_index_with_llamaparse
    result = await asyncio.to_thread(parse_index_with_llamaparse, pdf_bytes_b64, pages)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def validate_index_rows_tool(rows: list) -> str:
    """인덱스 행 스키마 검증 (dp_id, page_numbers 필수). rows는 parse_index_with_docling 반환의 sr_report_index."""
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import validate_index_rows
    result = await asyncio.to_thread(validate_index_rows, rows)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def detect_anomalies_tool(rows: list, total_pages: int) -> str:
    """인덱스 행 이상치 탐지. rows는 sr_report_index, total_pages는 get_pdf_metadata 반환값."""
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import detect_anomalies
    result = await asyncio.to_thread(detect_anomalies, rows, total_pages)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def correct_anomalous_rows_with_md_tool(anomalous_items: list, page_markdown: dict, report_id: str) -> str:
    """마크다운 기반 이상치 보정. page_markdown 키는 문자열 가능."""
    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import correct_anomalous_rows_with_md
    md_int = {int(k): (v or "") for k, v in (page_markdown or {}).items() if str(k).isdigit()}
    result = await asyncio.to_thread(correct_anomalous_rows_with_md, anomalous_items, md_int, report_id)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    import os

    if os.environ.get("MCP_HTTP") or os.environ.get("MCP_SR_INDEX_TOOLS_HTTP"):
        s = get_settings()
        port = int(os.environ.get("MCP_HTTP_PORT", str(s.mcp_http_port)))
        path = os.environ.get("MCP_HTTP_PATH", s.mcp_http_path)
        host = os.environ.get("MCP_HTTP_HOST", s.mcp_http_host)
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            path=path,
        )
    else:
        mcp.run()
