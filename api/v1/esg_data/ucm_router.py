"""ESG Data - UnifiedColumnMapping MVP API 라우터."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator


ucm_router = APIRouter(prefix="/ucm", tags=["ESG Data UCM"])


class CreateMappingsRequest(BaseModel):
    source_standard: str = Field(..., description="원본 기준서 (예: GRI)")
    target_standard: str = Field(..., description="대상 기준서 (예: ESRS)")
    vector_threshold: float = 0.70
    structural_threshold: float = 0.50
    final_threshold: float = 0.75
    batch_size: int = 40
    dry_run: bool = False


class SuggestMappingsRequest(BaseModel):
    source_standard: str = Field(..., description="원본 기준서")
    target_standard: str = Field(..., description="대상 기준서")
    vector_threshold: float = 0.70
    structural_threshold: float = 0.50
    final_threshold: float = 0.75
    limit: int = 100


class WorkflowCreateRequest(BaseModel):
    source_standard: str = Field(..., description="원본 기준서 (예: GRI)")
    target_standard: str = Field(..., description="대상 기준서 (예: ESRS)")
    vector_threshold: float = 0.70
    structural_threshold: float = 0.50
    final_threshold: float = 0.75
    batch_size: int = 40
    dry_run: bool = False
    run_quality_check: bool = True
    force_validate_only: bool = False


class PolicyPipelineRequest(BaseModel):
    source_standard: str = Field(..., description="원본 기준서")
    target_standard: str = Field(..., description="대상 기준서")
    batch_size: int = 40
    dry_run: bool = True
    top_k: int = 5
    vector_threshold: float = 0.70
    structural_threshold: float = 0.50
    final_threshold: float = 0.75
    use_llm_in_mapping_service: bool = False
    llm_model: str = "gpt-5-mini"


class NearestPipelineRequest(BaseModel):
    batch_size: int = 40
    dry_run: bool = True
    top_k: int = 5
    vector_threshold: float = 0.70
    structural_threshold: float = 0.50
    final_threshold: float = 0.75
    use_llm_in_mapping_service: bool = False
    llm_model: str = "gpt-5-mini"


@ucm_router.post("/create")
async def create_mappings(request: CreateMappingsRequest):
    """매핑 추천 배치를 실행하고(옵션) DB에 반영."""
    orchestrator = UCMOrchestrator()
    return orchestrator.create_mappings(
        source_standard=request.source_standard,
        target_standard=request.target_standard,
        vector_threshold=request.vector_threshold,
        structural_threshold=request.structural_threshold,
        final_threshold=request.final_threshold,
        batch_size=request.batch_size,
        dry_run=request.dry_run,
    )


@ucm_router.post("/suggest")
async def suggest_mappings(request: SuggestMappingsRequest):
    """저장 없이 매핑 후보 목록만 조회."""
    orchestrator = UCMOrchestrator()
    return orchestrator.suggest_mappings(
        source_standard=request.source_standard,
        target_standard=request.target_standard,
        vector_threshold=request.vector_threshold,
        structural_threshold=request.structural_threshold,
        final_threshold=request.final_threshold,
        limit=request.limit,
    )


@ucm_router.get("/health")
async def mapping_health():
    """매핑 상태 통계(정합성 지표) 조회."""
    orchestrator = UCMOrchestrator()
    return orchestrator.validate_mapping_health()


@ucm_router.post("/workflow/create")
async def create_mappings_workflow(request: WorkflowCreateRequest):
    """Phase 3 워크플로우(LangGraph 지원, 미설치 시 순차 폴백)로 생성+검증 수행."""
    orchestrator = UCMOrchestrator()
    return orchestrator.run_ucm_workflow(
        source_standard=request.source_standard,
        target_standard=request.target_standard,
        vector_threshold=request.vector_threshold,
        structural_threshold=request.structural_threshold,
        final_threshold=request.final_threshold,
        batch_size=request.batch_size,
        dry_run=request.dry_run,
        run_quality_check=request.run_quality_check,
        force_validate_only=request.force_validate_only,
    )


@ucm_router.post("/pipeline/policy")
async def run_policy_pipeline(request: PolicyPipelineRequest):
    """문서 §2 파이프라인: 임베딩→규칙검증→(옵션)LLM→정책→payload→upsert."""
    orchestrator = UCMOrchestrator()
    return orchestrator.run_ucm_policy_pipeline(
        source_standard=request.source_standard,
        target_standard=request.target_standard,
        batch_size=request.batch_size,
        dry_run=request.dry_run,
        top_k=request.top_k,
        vector_threshold=request.vector_threshold,
        structural_threshold=request.structural_threshold,
        final_threshold=request.final_threshold,
        use_llm_in_mapping_service=request.use_llm_in_mapping_service,
        llm_model=request.llm_model,
    )


@ucm_router.post("/pipeline/nearest")
async def run_nearest_pipeline(request: NearestPipelineRequest):
    """기준서 입력 없이: 다른 기준서만 최근접 후보로 §2 파이프라인 수행."""
    orchestrator = UCMOrchestrator()
    return orchestrator.run_ucm_nearest_pipeline(
        batch_size=request.batch_size,
        dry_run=request.dry_run,
        top_k=request.top_k,
        vector_threshold=request.vector_threshold,
        structural_threshold=request.structural_threshold,
        final_threshold=request.final_threshold,
        use_llm_in_mapping_service=request.use_llm_in_mapping_service,
        llm_model=request.llm_model,
    )

