# ESG 데이터 서비스 아키텍처

## 1. 개요

`esg_data` 서비스는 **UnifiedColumnMapping 생성/관리**와 **데이터 품질 검증**을 담당하는 통합 관리 서비스입니다.

핵심 목표:
- `data_points`, `rulebooks`를 기반으로 `unified_column_mappings` 자동 생성
- 소스 데이터(`environmental_data`, `social_data` 등)를 `sr_report_unified_data`로 통합
- 매핑 정합성 및 데이터 품질 검증

---

## 2. 아키텍처 패턴

### 2.1 레이어 구조

```
┌─────────────────────────────────────────────────────────┐
│  외부 클라이언트 / 에이전트                                │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP/SSE (Streamable)
┌────────────────▼────────────────────────────────────────┐
│  MCP Server (esg_tools_server.py, spokes/infra)          │
│  - FastMCP + Streamable HTTP                            │
│  - data_integration/sr_tools_server와 동일 패턴         │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  API Layer (backend/api/v1/esg_data)                    │
│  - FastAPI Router                                        │
│  - 요청 검증 및 응답 포맷팅                              │
└────────────────┬────────────────────────────────────────┘
                 │ In-process
┌────────────────▼────────────────────────────────────────┐
│  Orchestrator (hub/orchestrator)                         │
│  - UCMOrchestrator: 전체 플로우 조율                     │
│  - Phase 1: 단순 함수 체인                               │
│  - Phase 2: LangGraph 적용 (필요 시)                     │
└────────────────┬────────────────────────────────────────┘
                 │ In-process
┌────────────────▼────────────────────────────────────────┐
│  Routing Layer (hub/routing) [선택]                      │
│  - Agent 1개일 땐 생략                                   │
│  - 복수 agent 시 동적 선택                               │
└────────────────┬────────────────────────────────────────┘
                 │ In-process
┌────────────────▼────────────────────────────────────────┐
│  Agent Layer (spokes/agents)                             │
│  - ucm_creation_agent                                    │
│  - validation_agent (추후)                               │
│  - quality_check_agent (추후)                            │
└────────────────┬────────────────────────────────────────┘
                 │ In-process
┌────────────────▼────────────────────────────────────────┐
│  Tool Layer (spokes/infra)                               │
│  - UCMMappingService: esg_data 소유 ifrs DB/매핑 접근        │
│  - 기존 서비스 재사용                                    │
└────────────────┬────────────────────────────────────────┘
                 │ In-process
┌────────────────▼────────────────────────────────────────┐
│  Service Layer (ifrs_agent/service 재사용)               │
│  - MappingSuggestionService                              │
│  - EmbeddingService                                      │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Repository Layer (hub/repositories)                     │
│  - UnifiedColumnMappingRepository (재사용 권장)         │
│  - DataPointRepository                                   │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  Database (PostgreSQL + pgvector)                        │
│  - unified_column_mappings                               │
│  - data_points, rulebooks                                │
│  - sr_report_unified_data                                │
└─────────────────────────────────────────────────────────┘
```

### 2.2 통신 방식

| 레이어 간 | 방식 | 설명 |
|----------|------|------|
| 외부 → MCP Server | **Streamable HTTP** | FastMCP + SSE, `data_integration`와 동일 |
| MCP → API | In-process | 같은 프로세스 내 함수 호출 |
| API → Orchestrator | In-process | 직접 호출 |
| Orchestrator → Agent | In-process | 직접 호출 |
| Agent → Tool | In-process | 직접 호출 |
| Tool → Service | In-process | 직접 호출 |
| Service → Repository | In-process | 직접 호출 |

**장점**:
- 외부: MCP로 표준화된 접근
- 내부: 네트워크 오버헤드 없이 빠른 처리
- 디버깅 용이 (단일 프로세스)

---

## 3. 구현 Phase

### Phase 1: 단순 파이프라인 (MVP)

**목표**: 최소 기능으로 end-to-end 동작 확인

```
API → Orchestrator(단순 함수) → Service(재사용) → Repository → DB
```

**구현 항목**:
- [ ] API Router 기본 엔드포인트
- [ ] UCMOrchestrator (단순 함수 체인)
- [ ] ifrs_agent/service 재사용 연결
- [ ] Repository 래퍼 (ifrs_agent repo 재사용)
- [ ] 기본 테스트

**생략**:
- Agent/Tool 추상화
- Routing 레이어
- LangGraph

### Phase 2: Agent/Tool 분리

**목표**: 확장 가능한 구조로 전환

```
Orchestrator → Agent → Tool → Service
```

**구현 항목**:
- [ ] UCMCreationAgent 추가
- [ ] UCMMappingService 구현
- [ ] MCP 서버로 tool 노출
- [ ] Agent 단위 테스트

**선택**:
- LLM 판단 추가 (매핑 애매한 경우)
- Agent별 상태 관리

### Phase 3: 워크플로우 고도화

**목표**: 복잡한 조건 분기 지원

```
Orchestrator(LangGraph) → Routing → Agent pool
```

**구현 항목**:
- [ ] LangGraph StateGraph 적용
- [ ] Routing 레이어 추가
- [ ] 복수 Agent (validation, quality_check 등)
- [ ] 조건부 플로우 (if/else/loop)

---

## 4. 주요 컴포넌트 설계

### 4.1 MCP Server (외부 진입점)

**파일**: `backend/domain/v1/esg_data/spokes/infra/esg_tools_server.py`

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("esg-data-tools")

@mcp.tool()
async def create_unified_column_mapping(
    source_standard: str,
    target_standards: list[str],
    company_id: str | None = None,
    dry_run: bool = False
) -> dict:
    """
    DataPoints로부터 UnifiedColumnMapping 생성.
    
    Args:
        source_standard: 기준 기준서 (예: 'GRI')
        target_standards: 매핑 대상 기준서 목록 (예: ['IFRS_S2', 'ESRS'])
        company_id: 회사별 필터 (선택)
        dry_run: True면 저장 없이 후보만 반환
    
    Returns:
        {
            "status": "success" | "dry_run",
            "saved_count": int,
            "candidates": [...] (dry_run=True일 때)
        }
    """
    from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator
    
    orchestrator = UCMOrchestrator()
    result = await orchestrator.create_ucm_from_datapoints(
        source_standard=source_standard,
        target_standards=target_standards,
        company_id=company_id,
        dry_run=dry_run
    )
    return result

@mcp.tool()
async def validate_ucm_mappings(
    company_id: str | None = None
) -> dict:
    """
    UnifiedColumnMapping 정합성 검증.
    """
    from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator
    
    orchestrator = UCMOrchestrator()
    result = await orchestrator.validate_ucm_mappings(company_id=company_id)
    return result
```

### 4.2 API Router

**파일**: `backend/api/v1/esg_data/router.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/esg-data", tags=["esg-data"])

class CreateUCMRequest(BaseModel):
    source_standard: str
    target_standards: list[str]
    company_id: str | None = None
    dry_run: bool = False

@router.post("/ucm/create")
async def create_ucm(request: CreateUCMRequest):
    """
    UnifiedColumnMapping 생성 API.
    """
    from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator
    
    orchestrator = UCMOrchestrator()
    result = await orchestrator.create_ucm_from_datapoints(
        source_standard=request.source_standard,
        target_standards=request.target_standards,
        company_id=request.company_id,
        dry_run=request.dry_run
    )
    return result

@router.post("/ucm/validate")
async def validate_ucm(company_id: str | None = None):
    """
    UnifiedColumnMapping 검증 API.
    """
    from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator
    
    orchestrator = UCMOrchestrator()
    result = await orchestrator.validate_ucm_mappings(company_id=company_id)
    return result
```

### 4.3 Orchestrator (Phase 1)

**파일**: `backend/domain/v1/esg_data/hub/orchestrator/ucm_orchestrator.py`

```python
from typing import Optional
from backend.domain.v1.ifrs_agent.service.mapping_suggestion_service import (
    MappingSuggestionService
)
from backend.domain.v1.ifrs_agent.repository.unified_column_mapping_repository import (
    UnifiedColumnMappingRepository
)
from backend.domain.v1.ifrs_agent.repository.data_point_repository import (
    DataPointRepository
)

class UCMOrchestrator:
    """
    UnifiedColumnMapping 생성/관리 오케스트레이터.
    
    Phase 1: 단순 함수 체인
    Phase 2: Agent/Tool로 분리
    Phase 3: LangGraph 적용
    """
    
    def __init__(self):
        # 기존 서비스 재사용
        self.mapping_service = MappingSuggestionService()
        self.ucm_repo = UnifiedColumnMappingRepository()
        self.dp_repo = DataPointRepository()
    
    async def create_ucm_from_datapoints(
        self,
        source_standard: str,
        target_standards: list[str],
        company_id: Optional[str] = None,
        dry_run: bool = False
    ) -> dict:
        """
        DataPoints로부터 UnifiedColumnMapping 생성.
        
        플로우:
        1. 소스 기준서 DP 추출
        2. 타겟 기준서 DP와 유사도 매칭
        3. UCM 후보 생성
        4. (dry_run=False) DB 저장
        5. 결과 반환
        """
        # 1. 소스 DP 추출
        source_dps = await self.dp_repo.get_by_standard(source_standard)
        
        if not source_dps:
            return {
                "status": "error",
                "message": f"No DataPoints found for {source_standard}"
            }
        
        # 2. 매핑 후보 생성 (임베딩 기반 유사도)
        mappings = await self.mapping_service.suggest_mappings_batch(
            source_dps=source_dps,
            target_standards=target_standards,
            company_id=company_id
        )
        
        # 3. Dry-run 처리
        if dry_run:
            return {
                "status": "dry_run",
                "candidates": mappings,
                "count": len(mappings)
            }
        
        # 4. DB 저장
        saved = await self.ucm_repo.bulk_upsert(mappings)
        
        return {
            "status": "success",
            "saved_count": len(saved),
            "mappings": saved
        }
    
    async def validate_ucm_mappings(
        self,
        company_id: Optional[str] = None
    ) -> dict:
        """
        UnifiedColumnMapping 정합성 검증.
        
        검증 항목:
        - mapped_dp_ids의 DP 실존 여부
        - column_type vs data_type 일치
        - 중복 매핑 탐지
        - 단위 불일치
        """
        issues = []
        
        # UCM 조회
        ucms = await self.ucm_repo.get_all_active()
        
        for ucm in ucms:
            # mapped_dp_ids 검증
            for dp_id in ucm.mapped_dp_ids:
                dp = await self.dp_repo.get_by_id(dp_id)
                if not dp:
                    issues.append({
                        "type": "missing_dp",
                        "ucm_id": ucm.unified_column_id,
                        "dp_id": dp_id
                    })
        
        return {
            "status": "completed",
            "total_checked": len(ucms),
            "issues_count": len(issues),
            "issues": issues
        }
```

### 4.4 Tool Layer (Phase 2)

**파일**: `backend/domain/v1/esg_data/spokes/infra/ucm_mapping_service.py`

```python
class UCMMappingService:
    """ifrs_agent `MappingSuggestionService`·DB 세션을 감싼 인프로세스 퍼사드 (MCP tool과 별개)."""

    def create_mappings(self, source_standard: str, target_standard: str, *, dry_run: bool = False) -> dict:
        """배치 자동 추천 후 (dry_run이 아니면) DB 반영."""
        ...

    def suggest_mappings(self, source_standard: str, target_standard: str, **kwargs) -> dict:
        """저장 없이 후보 목록만 반환."""
        ...

    def validate_mappings(self) -> dict:
        """UCM·DataPoint 정합성 요약 통계."""
        ...
```

### 4.5 Agent Layer (Phase 2)

**파일**: `backend/domain/v1/esg_data/spokes/agents/ucm_creation_agent.py`

```python
class UCMCreationAgent:
    """
    UnifiedColumnMapping 생성 전문 Agent.
    
    Phase 2에서 추가.
    LLM 판단이 필요한 경우에만 활용.
    """
    
    def __init__(self):
        from backend.domain.v1.esg_data.spokes.infra.ucm_mapping_service import UCMMappingService
        self.mapping_service = UCMMappingService()
    
    def create_mappings(self, source_standard: str, target_standard: str, *, dry_run: bool = False) -> dict:
        """매핑 생성 — UCMMappingService(ifrs DB 연동)에 위임."""
        return self.mapping_service.create_mappings(
            source_standard, target_standard, dry_run=dry_run
        )

    # 향후: 다중 target_standard·저신뢰도 LLM 재평가 등은 여기서 분기
```

---

## 5. 기존 로직 재사용

### 5.1 MappingSuggestionService

**위치**: `backend/domain/v1/ifrs_agent/service/mapping_suggestion_service.py`

**재사용 방법**:
```python
# esg_data에서 직접 import
from backend.domain.v1.ifrs_agent.service.mapping_suggestion_service import (
    MappingSuggestionService
)

service = MappingSuggestionService()
result = await service.suggest_mappings_batch(...)
```

**주요 메서드**:
- `suggest_mappings_batch()`: 배치 매핑 제안
- `calculate_embedding_similarity()`: 임베딩 유사도
- `validate_mapping()`: 매핑 검증

### 5.2 auto_suggest_mappings_improved.py

**위치**: `backend/domain/v1/ifrs_agent/scripts/auto_suggest_mappings_improved.py`

**재사용 방법**:
```python
# 배치 처리 로직 참고
# Orchestrator에 통합
```

**핵심 로직**:
- 기준서별 DP 순회
- 임베딩 기반 유사도 계산
- 후보 필터링 + 저장

### 5.3 Repository

**권장**: `ifrs_agent`의 repository 직접 재사용

```python
# esg_data/hub/repositories/__init__.py

from backend.domain.v1.ifrs_agent.repository.unified_column_mapping_repository import (
    UnifiedColumnMappingRepository
)
from backend.domain.v1.ifrs_agent.repository.data_point_repository import (
    DataPointRepository
)

# 중복 방지
```

---

## 6. 디렉토리 구조

```
backend/domain/v1/esg_data/
├── docs/
│   ├── esg_data.md              # 서비스 개요
│   └── architecture.md          # 본 문서
├── api/                          # (또는 backend/api/v1/esg_data/)
│   └── router.py                # FastAPI 라우터
├── hub/
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   └── ucm_orchestrator.py  # 전체 플로우 조율
│   ├── routing/                 # Phase 3에서 추가
│   │   ├── __init__.py
│   │   └── agent_router.py      # Agent 선택 로직
│   └── repositories/            # (또는 ifrs_agent repo 재사용)
│       ├── __init__.py
│       └── ...
├── spokes/
│   ├── agents/                  # Phase 2에서 추가
│   │   ├── __init__.py
│   │   ├── ucm_creation_agent.py
│   │   ├── validation_agent.py  # 추후
│   │   └── quality_check_agent.py  # 추후
│   └── infra/
│       ├── __init__.py
│       ├── esg_tools_server.py  # MCP 서버
│       └── ucm_mapping_service.py  # ifrs DB/매핑 (esg_data 소유)
├── models/
│   ├── bases/                   # (또는 ifrs_agent models 재사용)
│   │   └── ...
│   ├── states/                    # 레거시 placeholder
│   └── langgraph/
│       └── ucm_workflow_state.py  # Phase 3: LangGraph용
├── __init__.py
└── main.py                      # (선택) 독립 실행용
```

---

## 7. data_integration과의 비교

| 항목 | data_integration | esg_data |
|------|------------------|----------|
| **목적** | SR 보고서 본문 생성 | UCM 생성 + 데이터 품질 관리 |
| **Orchestrator** | LangGraph StateGraph | Phase 1: 단순 함수, Phase 3: LangGraph |
| **Agent** | sr_agent (LLM 중심) | ucm_creation_agent (로직 중심, LLM 선택) |
| **Tool** | sr_tools (PDF, RAG 등) | UCM 파이프라인 Tool + UCMMappingService |
| **MCP 서버** | sr_tools_server (Streamable HTTP) | esg_tools_server (Streamable HTTP) |
| **내부 통신** | In-process | In-process |
| **Service 재사용** | 자체 서비스 | ifrs_agent/service 재사용 |

**공통점**:
- MCP Streamable HTTP (외부 접근)
- In-process (내부 통신)
- FastMCP 사용

**차이점**:
- `esg_data`는 초기엔 더 단순 (LLM 선택적)
- `data_integration`은 대화형 Agent 중심

---

## 8. 구현 우선순위

### 8.1 필수 (Phase 1)

1. API Router 기본 엔드포인트
2. UCMOrchestrator (단순 함수 체인)
3. ifrs_agent 서비스 재사용 연결
4. 테스트 코드

### 8.2 권장 (Phase 2)

1. MCP 서버 구현
2. Tool 래퍼
3. Agent 추상화 (LLM 판단 추가)

### 8.3 선택 (Phase 3)

1. LangGraph 적용
2. Routing 레이어
3. 복수 Agent
4. 복잡한 조건 분기

---

## 9. 테스트 전략

### 9.1 단위 테스트

```python
# tests/unit/test_ucm_orchestrator.py

import pytest
from backend.domain.v1.esg_data.hub.orchestrator import UCMOrchestrator

@pytest.mark.asyncio
async def test_create_ucm_dry_run():
    orchestrator = UCMOrchestrator()
    result = await orchestrator.create_ucm_from_datapoints(
        source_standard="GRI",
        target_standards=["IFRS_S2"],
        dry_run=True
    )
    
    assert result["status"] == "dry_run"
    assert "candidates" in result
    assert result["count"] > 0

@pytest.mark.asyncio
async def test_validate_mappings():
    orchestrator = UCMOrchestrator()
    result = await orchestrator.validate_ucm_mappings()
    
    assert result["status"] == "completed"
    assert "issues_count" in result
```

### 9.2 통합 테스트

```python
# tests/integration/test_ucm_flow.py

@pytest.mark.asyncio
async def test_full_ucm_creation_flow():
    """End-to-end 플로우 테스트."""
    orchestrator = UCMOrchestrator()
    
    # 1. 생성
    result = await orchestrator.create_ucm_from_datapoints(
        source_standard="GRI",
        target_standards=["IFRS_S2"],
        dry_run=False
    )
    assert result["status"] == "success"
    
    # 2. 검증
    validation = await orchestrator.validate_ucm_mappings()
    assert validation["issues_count"] == 0
```

---

## 10. 성능 고려사항

### 10.1 In-process 장점

- **지연 시간**: 네트워크 홉 없음 (~1ms vs ~50ms)
- **처리량**: 직접 함수 호출로 높은 TPS
- **디버깅**: 단일 프로세스라 breakpoint 용이

### 10.2 병렬 처리

```python
# 배치 처리 최적화

import asyncio

async def create_ucm_for_multiple_standards(
    standards: list[str]
) -> dict:
    """여러 기준서 병렬 처리."""
    tasks = [
        orchestrator.create_ucm_from_datapoints(
            source_standard=std,
            target_standards=["IFRS_S2"]
        )
        for std in standards
    ]
    results = await asyncio.gather(*tasks)
    return {"results": results}
```

### 10.3 캐싱 전략

```python
# 임베딩 캐싱 (MappingSuggestionService 내부)
# DB에 이미 저장된 임베딩 재사용
```

---

## 11. 보안 및 권한

### 11.1 API 인증

```python
from fastapi import Depends, HTTPException
from backend.auth import get_current_user

@router.post("/ucm/create")
async def create_ucm(
    request: CreateUCMRequest,
    user = Depends(get_current_user)  # 인증 필수
):
    if not user.has_permission("esg_data.ucm.write"):
        raise HTTPException(403, "Permission denied")
    ...
```

### 11.2 회사별 격리

```python
# company_id 필터링으로 멀티테넌트 지원
result = await orchestrator.create_ucm_from_datapoints(
    source_standard="GRI",
    target_standards=["IFRS_S2"],
    company_id=user.company_id  # 사용자 회사로 제한
)
```

---

## 12. 모니터링 및 로깅

### 12.1 구조화 로깅

```python
import structlog

logger = structlog.get_logger()

async def create_ucm_from_datapoints(...):
    logger.info(
        "ucm_creation_started",
        source_standard=source_standard,
        target_standards=target_standards,
        dry_run=dry_run
    )
    
    result = ...
    
    logger.info(
        "ucm_creation_completed",
        status=result["status"],
        saved_count=result.get("saved_count", 0)
    )
    
    return result
```

### 12.2 메트릭

```python
from prometheus_client import Counter, Histogram

ucm_creation_counter = Counter(
    "esg_data_ucm_creations_total",
    "Total UCM creations",
    ["status"]
)

ucm_creation_duration = Histogram(
    "esg_data_ucm_creation_duration_seconds",
    "UCM creation duration"
)
```

---

## 13. 향후 확장 계획

### 13.1 자동 UCM 승격

```python
# unmapped_data_points → unified_column_mappings 자동 전환
# 조건:
# - mapping_status == 'reviewing'
# - mapping_confidence > 0.8
# - LLM 최종 승인
```

### 13.2 품질 점수 자동 산정

```python
# sr_report_unified_data.confidence_score 자동 계산
# 기준:
# - 소스 데이터 최신성
# - 매핑 신뢰도
# - 값 범위 준수
```

### 13.3 이상 탐지 자동화

```python
# data_quality_issues 테이블 신설
# 일간 배치로 자동 검증 + 알림
```

---

## 14. FAQ

### Q1. Agent 없이 바로 Service 호출하면 안 되나요?

**A**: Phase 1에서는 그렇게 합니다. Agent는 Phase 2부터 추가하며, 주로 LLM 판단이 필요한 경우에만 사용합니다.

### Q2. data_integration처럼 LangGraph를 처음부터 써야 하나요?

**A**: 아니요. UCM 생성은 단순 플로우라 처음엔 함수 체인으로 충분합니다. 조건 분기가 복잡해지면 Phase 3에서 적용합니다.

### Q3. MCP 서버를 꼭 만들어야 하나요?

**A**: 외부 에이전트가 접근할 예정이라면 권장합니다. 내부 API만 쓴다면 생략 가능합니다.

### Q4. Repository를 esg_data에 복사해야 하나요?

**A**: 아니요. `ifrs_agent`의 repository를 직접 import해서 재사용하는 것이 좋습니다.

### Q5. Streamable HTTP는 왜 필요한가요?

**A**: 실시간 진행상황(스트리밍)을 외부 클라이언트에 전달하기 위함입니다. `data_integration`과 동일한 패턴입니다.

---

## 15. 참고 자료

- [ESG 데이터 서비스 설계](./esg_data.md)
- [UCM 결정/정책 모듈 설계](./UCM_DECISION_POLICY_DESIGN.md)
- [DATABASE_TABLES_STRUCTURE.md](../../ifrs_agent/docs/DATABASE_TABLES_STRUCTURE.md)
- [DATA_ONTOLOGY.md](../../ifrs_agent/docs/DATA_ONTOLOGY.md)
- [data_integration 구조](../../data_integration/)
- [MappingSuggestionService](../../ifrs_agent/service/mapping_suggestion_service.py)

---

**작성일**: 2026-03-24  
**버전**: 1.0  
**상태**: 초안
