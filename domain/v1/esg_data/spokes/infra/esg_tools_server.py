"""ESG data tools MCP server (Phase 2)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator

mcp = FastMCP("esg-data-tools")


@mcp.tool()
async def create_unified_column_mapping(
    source_standard: str,
    target_standard: str,
    vector_threshold: float = 0.70,
    structural_threshold: float = 0.50,
    final_threshold: float = 0.75,
    batch_size: int = 40,
    dry_run: bool = False,
) -> dict:
    """DataPoints 기반 UnifiedColumnMapping 생성."""
    orchestrator = UCMOrchestrator()
    return orchestrator.create_mappings(
        source_standard=source_standard,
        target_standard=target_standard,
        vector_threshold=vector_threshold,
        structural_threshold=structural_threshold,
        final_threshold=final_threshold,
        batch_size=batch_size,
        dry_run=dry_run,
    )


@mcp.tool()
async def validate_ucm_mappings() -> dict:
    """UnifiedColumnMapping 정합성 검증."""
    orchestrator = UCMOrchestrator()
    return orchestrator.validate_mapping_health()


@mcp.tool()
async def run_ucm_workflow(
    source_standard: str,
    target_standard: str,
    vector_threshold: float = 0.70,
    structural_threshold: float = 0.50,
    final_threshold: float = 0.75,
    batch_size: int = 40,
    dry_run: bool = False,
    run_quality_check: bool = True,
    force_validate_only: bool = False,
) -> dict:
    """Phase 3 UCM 워크플로우(생성→검증→품질 요약) 실행."""
    orchestrator = UCMOrchestrator()
    return orchestrator.run_ucm_workflow(
        source_standard=source_standard,
        target_standard=target_standard,
        vector_threshold=vector_threshold,
        structural_threshold=structural_threshold,
        final_threshold=final_threshold,
        batch_size=batch_size,
        dry_run=dry_run,
        run_quality_check=run_quality_check,
        force_validate_only=force_validate_only,
    )


@mcp.tool()
async def run_ucm_mapping_pipeline(
    source_standard: str,
    target_standard: str,
    batch_size: int = 40,
    dry_run: bool = True,
    top_k: int = 5,
    vector_threshold: float = 0.70,
    structural_threshold: float = 0.50,
    final_threshold: float = 0.75,
    use_llm_in_mapping_service: bool = False,
    llm_model: str = "gpt-5-mini",
) -> dict:
    """§2 파이프라인(임베딩→규칙→LLM→정책→payload→upsert) 실행."""
    orchestrator = UCMOrchestrator()
    return orchestrator.run_ucm_policy_pipeline(
        source_standard=source_standard,
        target_standard=target_standard,
        batch_size=batch_size,
        dry_run=dry_run,
        top_k=top_k,
        vector_threshold=vector_threshold,
        structural_threshold=structural_threshold,
        final_threshold=final_threshold,
        use_llm_in_mapping_service=use_llm_in_mapping_service,
        llm_model=llm_model,
    )


@mcp.tool()
async def run_ucm_nearest_pipeline(
    batch_size: int = 40,
    dry_run: bool = True,
    top_k: int = 5,
    vector_threshold: float = 0.70,
    structural_threshold: float = 0.50,
    final_threshold: float = 0.75,
    use_llm_in_mapping_service: bool = False,
    llm_model: str = "gpt-5-mini",
) -> dict:
    """기준서 입력 없이: 다른 기준서만 최근접 후보로 §2 파이프라인 수행."""
    orchestrator = UCMOrchestrator()
    return orchestrator.run_ucm_nearest_pipeline(
        batch_size=batch_size,
        dry_run=dry_run,
        top_k=top_k,
        vector_threshold=vector_threshold,
        structural_threshold=structural_threshold,
        final_threshold=final_threshold,
        use_llm_in_mapping_service=use_llm_in_mapping_service,
        llm_model=llm_model,
    )


if __name__ == "__main__":
    mcp.run()
