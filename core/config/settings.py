"""공통 설정 로더.

여러 도메인(ifrs_agent, esg_data, data_integration)에서 재사용한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _env_flag_default_true(key: str, *, default: bool = True) -> bool:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() not in ("0", "false", "off", "no")


def _env_flag_false_by_default(key: str) -> bool:
    raw = os.getenv(key, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Common
    embedding_model: str = "BAAI/bge-m3"
    database_url: str = ""
    groq_api_key: str = ""
    mcp_sr_index_tools_url: str = ""
    groq_temperature: float = 0.2
    groq_max_tokens: int = 4096
    max_retries: int = 3

    # Domain defaults (ifrs_agent 등)
    rag_model: str = "llama-3.3-70b-versatile"
    supervisor_model: str = "llama-3.3-70b-versatile"
    dart_api_key: str = ""
    tavily_api_key: str = ""

    # data_integration — MCP
    mcp_internal_transport: str = "inprocess"
    mcp_sr_tools_url: str = ""
    mcp_sr_body_tools_url: str = ""
    mcp_sr_images_tools_url: str = ""
    mcp_web_search_url: str = ""
    mcp_http_host: str = "127.0.0.1"
    mcp_http_port: int = 8000
    mcp_http_path: str = "/mcp"

    # data_integration — LLM / 파싱
    openai_api_key: str = ""
    llama_cloud_api_key: str = ""

    # data_integration — SR 이미지
    sr_image_storage: str = "memory"
    sr_image_output_dir: str = ""
    sr_image_vlm_auto_after_save: bool = True

    # data_integration — S3 / MinIO
    sr_s3_bucket: str = ""
    sr_s3_prefix: str = "sr-images/"
    aws_region: str = "ap-northeast-2"
    s3_endpoint_url: str = ""

    # data_integration — API 서버
    data_integration_reload: bool = False
    data_integration_port: int = 9002


def _load_env() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_path = project_root / ".env"
    if env_path.exists():
        try:
            load_dotenv(env_path, encoding="utf-8")
        except UnicodeDecodeError:
            try:
                load_dotenv(env_path, encoding="utf-16")
            except Exception:
                load_dotenv(env_path)


def _s3_bucket_resolved() -> str:
    return (os.getenv("SR_S3_BUCKET") or os.getenv("AWS_S3_BUCKET") or "").strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env()
    http_host = os.getenv("MCP_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    http_port = int(os.getenv("MCP_HTTP_PORT", "8000"))
    http_path = os.getenv("MCP_HTTP_PATH", "/mcp").strip() or "/mcp"

    port_raw = os.getenv("PORT") or os.getenv("DATA_INTEGRATION_PORT", "9002")
    data_integration_port = int(str(port_raw).strip())

    return Settings(
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
        database_url=os.getenv("DATABASE_URL", ""),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        mcp_sr_index_tools_url=os.getenv("MCP_SR_INDEX_TOOLS_URL", ""),
        groq_temperature=float(os.getenv("GROQ_TEMPERATURE", "0.2")),
        groq_max_tokens=int(os.getenv("GROQ_MAX_TOKENS", "4096")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        rag_model=os.getenv("RAG_MODEL", "llama-3.3-70b-versatile"),
        supervisor_model=os.getenv("SUPERVISOR_MODEL", "llama-3.3-70b-versatile"),
        dart_api_key=os.getenv("DART_API_KEY", ""),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        mcp_internal_transport=os.getenv("MCP_INTERNAL_TRANSPORT", "inprocess").strip() or "inprocess",
        mcp_sr_tools_url=os.getenv("MCP_SR_TOOLS_URL", ""),
        mcp_sr_body_tools_url=os.getenv("MCP_SR_BODY_TOOLS_URL", ""),
        mcp_sr_images_tools_url=os.getenv("MCP_SR_IMAGES_TOOLS_URL", ""),
        mcp_web_search_url=os.getenv("MCP_WEB_SEARCH_URL", ""),
        mcp_http_host=http_host,
        mcp_http_port=http_port,
        mcp_http_path=http_path,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        llama_cloud_api_key=os.getenv("LLAMA_CLOUD_API_KEY", ""),
        sr_image_storage=(os.getenv("SR_IMAGE_STORAGE", "memory").strip().lower() or "memory"),
        sr_image_output_dir=os.getenv("SR_IMAGE_OUTPUT_DIR", "").strip(),
        sr_image_vlm_auto_after_save=_env_flag_default_true("SR_IMAGE_VLM_AUTO_AFTER_SAVE", default=True),
        sr_s3_bucket=_s3_bucket_resolved(),
        sr_s3_prefix=(os.getenv("SR_S3_PREFIX") or "sr-images/").strip() or "sr-images/",
        aws_region=(
            os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-northeast-2"
        ).strip() or "ap-northeast-2",
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", "").strip(),
        data_integration_reload=_env_flag_false_by_default("DATA_INTEGRATION_RELOAD"),
        data_integration_port=data_integration_port,
    )
