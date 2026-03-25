# UCM 파이프라인 구현 가이드: Tool 개수, Agent, MCP·인프로세스 전략

## 1. 문서 목적

[UCM_DECISION_POLICY_DESIGN.md](./UCM_DECISION_POLICY_DESIGN.md) §2의 **권장 파이프라인 6단계**를 실제 코드로 옮길 때 필요한 **Tool 개수**, **Agent 설계·구현 방법**, **MCP와 인프로세스 호출 경계**를 한곳에 정리한다.

상위 맥락: [architecture.md](./architecture.md), [UCM_DATAPOINT_RULEBOOK_EXTRACTION_GUIDE.md](../../ifrs_agent/docs/UCM_DATAPOINT_RULEBOOK_EXTRACTION_GUIDE.md)(데이터 품질).

---

## 2. “생성해야 하는 Tool”은 몇 개인가?

### 2.1 정의 구분

| 구분 | 의미 |
|------|------|
| **인프로세스 Tool** | 계산·검증·변환만 담당하는 **Python 모듈/클래스**(테스트·오케스트레이터가 직접 호출). 문서 §2의 1·2·5단계에 대응. |
| **(선택) LLM 호출 래퍼** | §2의 3단계. 별도 클래스로 두면 모의(mock)와 비용 게이트 테스트가 쉬움. |
| **Agent 정책 모듈** | §2의 4단계. Tool이 아니라 **판단 로직**(accept / review / reject). |
| **Orchestrator + Repository** | §2의 6단계. Tool이 아니라 **흐름 제어·저장**. |

### 2.2 권장 답: **인프로세스 Tool 모듈 4개**

| # | Tool (모듈) | 대응 파이프라인 단계 | 역할 요약 |
|---|-------------|---------------------|-----------|
| 1 | **EmbeddingCandidateTool** | §2-1 | 소스 DP·타깃 기준서·`top_k` 입력 → 벡터 검색으로 후보 `dp_id` 목록, `embedding_score`, 순위, (선택) 근거 텍스트. |
| 2 | **RuleValidationTool** | §2-2 | 소스 DP + 후보 목록 + (조인된) rulebook 메타 → `rule_pass`, `rule_score`, `violations[]`, `rule_evidence`. §4 결합 키(`primary_dp_id`, `related_dp_ids`) 반영. |
| 3 | **LLMRefinementTool** (선택·권장 분리) | §2-3 | 경계 구간에서만 호출. 소스/타깃 DP 요약 + rulebook 발췌 → 보조 점수·코멘트·`review` 보정용 출력. **호출 여부는 Agent 정책이 결정.** |
| 4 | **SchemaMappingTool** | §2-5 | §2-4에서 확정된 매핑 → `unified_column_mappings` **upsert용 payload** (`mapped_dp_ids`, `mapping_confidence`, `mapping_status`, `reason_codes`, `evidence` 등). **DB 쓰기 없음.** |

**정리:** 구현 단위로는 **4개의 Tool(모듈)** 을 두는 것을 권장한다.  
- §2-4는 Tool이 아니다 → **Agent 내부 정책 모듈**  
- §2-6은 Tool이 아니다 → **Orchestrator → Repository**

### 2.3 LLM을 Tool에서 빼고 Agent에만 둘 수 있나?

가능하지만, 테스트·스텁·호출 횟수 계측을 위해 **3단계 LLM은 별도 `LLMRefinementTool`(또는 `infra` 클라이언트)로 두는 편**이 [UCM_DECISION_POLICY_DESIGN.md](./UCM_DECISION_POLICY_DESIGN.md) §9의 책임 분리·테스트 전략과 잘 맞는다.

---

## 3. 6단계 파이프라인과 코드 배치 (권장)

```
[§2-1] EmbeddingCandidateTool
    → 후보 리스트
[§2-2] RuleValidationTool  (datapoint + rulebook 조인 데이터 입력)
    → 규칙 점수·위반
[§2-3] LLMRefinementTool   (정책이 true일 때만)
    → 보조 판단 신호
[§2-4] UCMCreationAgent._decide_* (정책 모듈)
    → DecisionResult: accept | review | reject
[§2-5] SchemaMappingTool
    → upsert payload
[§2-6] UCMOrchestrator → UnifiedColumnMappingRepository (또는 기존 ifrs_agent 저장 경로)
    → commit
```

권장 파일 위치(예시, 프로젝트 관례에 맞게 조정 가능):

| 구성요소 | 권장 경로 |
|----------|-----------|
| EmbeddingCandidateTool | `backend/domain/shared/tool/UnifiedColumnMapping/ucm_embedding_tool.py` |
| RuleValidationTool | `backend/domain/shared/tool/UnifiedColumnMapping/ucm_rule_validation_tool.py` |
| LLM 재평가 | `UCMCreationAgent.llm_refinement` (§2-3, 스텁·확장 지점) |
| SchemaMappingTool | `backend/domain/shared/tool/UnifiedColumnMapping/ucm_schema_mapping_tool.py` |
| MCP (ESG UCM) | `backend/domain/v1/esg_data/spokes/infra/esg_tools_server.py` |
| 계약(TypedDict) | `backend/domain/v1/esg_data/spokes/infra/ucm_pipeline_contracts.py` |
| LangGraph 상태 | `backend/domain/v1/esg_data/models/langgraph/ucm_workflow_state.py` |
| ifrs DB/서비스 접근 | `UCMMappingService` — `backend/domain/v1/esg_data/spokes/infra/ucm_mapping_service.py` |
| Agent 정책 | `backend/domain/v1/esg_data/spokes/agents/ucm_creation_agent.py` (내부 메서드로 확장) |
| Orchestrator | `backend/domain/v1/esg_data/hub/orchestrator/ucm_orchestrator.py` |

DB·세션·기존 `MappingSuggestionService`와의 연동은 **Tool 내부** 또는 **얇은 Facade**에서 수행하고, Agent는 **순수 판단 입력(JSON-like dict)** 만 받도록 유지한다.

---

## 4. Agent 설계 및 구현 방법

### 4.1 역할

- **Tool은 판단하지 않는다.** 점수·위반·payload 생성만 한다.
- **Agent는 정책만 실행한다.** §5 점수식, §7 임계값, 치명 위반 우선, LLM 호출 게이트(`_should_call_llm`).

### 4.2 권장 내부 API (문서 §6과 정렬)

`UCMCreationAgent`에 다음을 두는 것을 권장한다.

- `_decide_candidate(scores, violations, policy_version) -> DecisionResult`
- `_should_call_llm(embedding_score, rule_result, tentative_decision) -> bool`
- `_refine_with_llm(context) -> LLMRefinementResult` (실제 호출은 `LLMRefinementTool`에 위임)

`DecisionResult` 필드: `decision`, `confidence`, `reason_codes`, `llm_used`, `evidence` (문서 §6).

### 4.3 배치 vs 단건

- **단건 DP 매핑 검증·시드 생성**: 위 파이프라인을 DP 단위로 반복.
- **배치**: Orchestrator가 `batch_size`만큼 DP를 돌리되, 각 DP마다 동일 파이프라인; 실패 시 해당 DP만 롤백 또는 큐 적재(운영 정책).

### 4.4 기존 코드와의 관계

- 현재 `MappingSuggestionService.auto_suggest_mappings_batch`는 **DP `equivalent_dps` 갱신** 중심이며, §2의 4·5·6단계(정책·UCM payload·명시적 upsert)와 **완전히 일치하지 않는다**.
- 이 문서의 파이프라인은 **신규 Tool 체인**으로 구현하고, 성숙 후 기존 배치와 **병행·대체** 전략을 택하면 된다.

---

## 5. MCP vs 인프로세스 전송 전략

### 5.1 원칙 (architecture.md와 동일)

| 경계 | 방식 | 용도 |
|------|------|------|
| **외부 클라이언트 ↔ 백엔드** | MCP (FastMCP, Streamable HTTP 등) | 다른 프로세스의 에이전트·IDE·스크립트가 UCM 작업을 **표준 API**로 호출 |
| **MCP 핸들러 ↔ 도메인** | **인프로세스 직접 호출** | 같은 Python 프로세스 내에서 Orchestrator/Agent/Tool 호출 — **직렬화·네트워크 없음** |
| **FastAPI ↔ 도메인** | **인프로세스 직접 호출** | MCP와 동일 Orchestrator 진입점 공유 권장 |

### 5.2 MCP에 몇 개의 `@mcp.tool()`을 노출할지

두 가지 패턴이 모두 유효하다.

**패턴 A — 얇은 MCP (권장 초기)**  
- MCP Tool **1~3개**만 노출: 예) `run_ucm_mapping_pipeline`, `validate_ucm_health`, `dry_run_ucm_candidates`  
- 내부에서는 §2의 **4개 인프로세스 Tool**을 Orchestrator가 순서대로 호출.  
- **장점**: 외부 계약 단순, 버전 관리 쉬움.

**패턴 B — 디버깅용 두꺼운 MCP**  
- 인프로세스 Tool과 1:1로 MCP Tool을 **최대 4개** 노출 (임베딩만, 규칙만 등).  
- **장점**: 단계별 재현·테스트 용이. **단점**: 클라이언트가 조합 책임을 점.

운영 환경에서는 **패턴 A**, 개발·진단에서는 **패턴 B를 추가**하는 하이브리드도 가능하다.

### 5.3 인프로세스 “전송”이란 무엇인가

- 단계 간 데이터는 **Pydantic 모델 또는 TypedDict**로 고정한다.
- Tool 간에는 **dict 전달**로 충분하며, MCP JSON 직렬화는 **MCP 경계에서만** 발생한다.
- 대용량 rulebook 본문은 전 단계에 실어 나르지 말고, **rulebook_id + 발췌 스니펫** 또는 **이미 조인된 요약 필드**만 전달해 메모리·토큰을 절약한다.

### 5.4 보안·멀티테넌트

- MCP/FastAPI 진입점에서 `company_id`·인증을 검증한 뒤, Orchestrator에 전달.
- Tool은 **세션/DB 읽기**만 하고, 권한 필터는 Repository 또는 Facade 단일 지점에서 적용.

---

## 6. 구현 순서 (문서 §11과 통합)

1. **EmbeddingCandidateTool** 인터페이스·단위 테스트 (기존 벡터 검색 로직 래핑)
2. **RuleValidationTool** + rulebook·datapoint 조인 (§4 결합 키)
3. **UCMCreationAgent** 정책 모듈 + `LLMRefinementTool` 스텁
4. **SchemaMappingTool** + payload 스키마 고정
5. **UCMOrchestrator**에서 1→2→(3)→4→5→6 연결 및 `dry_run` 플래그
6. MCP: `run_ucm_mapping_pipeline` 단일 도구로 노출 (패턴 A)
7. `reviewing` 큐·리포트·메트릭 (운영)

---

## 7. 관련 문서

- [UCM_DECISION_POLICY_DESIGN.md](./UCM_DECISION_POLICY_DESIGN.md) — 6단계 파이프라인, 점수식, 판정 정책
- [architecture.md](./architecture.md) — Hub/Spokes, MCP vs 인프로세스
- [UCM_DATAPOINT_RULEBOOK_EXTRACTION_GUIDE.md](../../ifrs_agent/docs/UCM_DATAPOINT_RULEBOOK_EXTRACTION_GUIDE.md) — 시드 데이터 품질

---

**작성일**: 2026-03-25  
**상태**: 구현 가이드 초안  

**구현 반영(코드)**: 계약·워크플로 결과 TypedDict `esg_data/spokes/infra/ucm_pipeline_contracts.py`; LangGraph 상태 `esg_data/models/langgraph/ucm_workflow_state.py`; Tool 3종 `shared/tool/UnifiedColumnMapping/`; `UCMMappingService`·MCP `esg_data/spokes/infra/`; LLM 스텁 `UCMCreationAgent.llm_refinement`. 정책 `spokes/agents/ucm_policy.py`, `UCMOrchestrator.run_ucm_policy_pipeline`, API `POST /esg-data/ucm/pipeline/policy`, MCP `run_ucm_mapping_pipeline`.
