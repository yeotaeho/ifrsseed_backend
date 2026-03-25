# UCM 결정/정책 모듈 설계 (Agent 내부)

## 1. 목적

`UnifiedColumnMapping` 채움 로직에서 품질/재현성/비용을 동시에 확보하기 위해, 아래 원칙을 사용한다.

- 후보 생성과 검증은 **Tool**에서 수행
- 최종 `accept/review/reject` 판단은 **Agent 내부 정책 모듈**에서 수행
- LLM은 경계 구간에서만 보조 판단에 사용

이 문서는 `backend/domain/v1/esg_data/spokes/agents/ucm_creation_agent.py`를 중심으로 한 판단 정책을 정의한다.

---

## 2. 권장 파이프라인

1) 임베딩 후보 생성 Tool  
2) 규칙 검증 Tool  
3) (선택) 경계 구간 LLM 재평가  
4) Agent 정책 모듈 최종 판정  
5) 스키마 매핑 Tool로 저장용 payload 생성  
6) Orchestrator -> Repository로 upsert

핵심 원칙:
- Tool은 "계산/검증/변환"만 담당
- Agent는 "정책 판단"만 담당
- Repository는 "저장"만 담당

---

## 3. Tool 구성 (MVP)

## 3.1 Embedding Tool
- 입력: source DP, target standard, top_k
- 출력:
  - `candidate_dp_id`
  - `embedding_score` (0.0~1.0)
  - `rank`
  - `embedding_evidence` (선택)

## 3.2 Rule Validation Tool
- 입력: source DP + 후보 목록
- 출력:
  - `rule_pass` (bool)
  - `rule_score` (0.0~1.0)
  - `violations[]` (예: `unit_mismatch`, `category_conflict`, `data_type_conflict`)
  - `rule_evidence` (선택)

## 3.3 Schema Mapping Tool
- 입력: Agent가 최종 채택한 후보/판정 결과
- 출력:
  - `unified_column_mappings` upsert용 payload
  - 공통 필드 예: `mapped_dp_ids`, `mapping_confidence`, `mapping_status`, `reason_codes`, `evidence`

주의:
- Schema Mapping Tool은 저장을 하지 않는다.
- 저장은 Orchestrator -> Repository에서 수행한다.

---

## 4. `rulebook + data_point` 결합 전략

`data_point.json` 단독 사용보다 `rulebook.json`을 결합해 의미/규칙 문맥을 함께 평가한다.

## 4.1 결합 키
- 기본 조인 키: `rulebook.primary_dp_id == data_point.dp_id`
- 후보 확장 키: `rulebook.related_dp_ids[]`

## 4.2 결합 목적
- `data_point`: 식별자/이름/카테고리/타입/계층(정의 정보)
- `rulebook`: 요구사항/검증조건/핵심 키워드(판단 정보)

## 4.3 결합 후 평가 입력 예시
- 임베딩 점수: source DP vs target DP
- 규칙 정합 점수: `validation_rules.key_terms`, `required_actions`, `verification_checks`
- 요구 강도 가중치: `disclosure_requirement` (`필수` 여부)
- 구조 정합: category/dp_type/unit 충돌 여부

---

## 5. 결합 점수식(가중치 제안)

최종 점수는 0~1 범위로 정규화한다.

```text
final_score
 = 0.50 * embedding_score
 + 0.30 * rule_score
 + 0.10 * structure_score
 + 0.10 * requirement_score
 - penalty
```

- `embedding_score`: 임베딩 유사도 (후보 검색 점수)
- `rule_score`: rulebook 기반 의미/요구사항 충족 점수
- `structure_score`: category, dp_type, unit 정합성 점수
- `requirement_score`: 필수 공시/우선순위 반영 점수
- `penalty`: 치명 충돌/강한 불일치 페널티

## 5.1 가중치 표(초안)

| 항목 | 기호 | 범위 | 가중치 | 비고 |
|---|---|---|---:|---|
| 임베딩 유사도 | `embedding_score` | 0~1 | 0.50 | 후보 리콜 중심 |
| 규칙 정합성 | `rule_score` | 0~1 | 0.30 | rulebook 핵심 |
| 구조 정합성 | `structure_score` | 0~1 | 0.10 | 타입/단위/카테고리 |
| 요구 강도 | `requirement_score` | 0~1 | 0.10 | `disclosure_requirement` 반영 |
| 페널티 | `penalty` | 0~0.50 | - | 치명 위반 시 가산 감점 |

## 5.2 페널티 규칙(권장)
- `critical_rule_fail` (예: 필수 조건 미충족): `penalty += 0.30`
- `data_type_conflict` (정량/정성 불일치): `penalty += 0.20`
- `unit_mismatch` (정량 단위 불일치, 변환 불가): `penalty += 0.10`
- `category_conflict` (E/S/G 영역 충돌): `penalty += 0.10`

---

## 6. Agent 내부 정책 모듈

위치:
- `backend/domain/v1/esg_data/spokes/agents/ucm_creation_agent.py`

권장 내부 함수:
- `_decide_candidate(...) -> DecisionResult`
- `_should_call_llm(...) -> bool`
- `_refine_with_llm(...) -> DecisionResult`

`DecisionResult` 권장 필드:
- `decision`: `accept | review | reject`
- `confidence`: float
- `reason_codes`: list[str]
- `llm_used`: bool
- `evidence`: dict

---

## 7. 판정 정책 (초안)

하드 규칙(우선):
- 치명적 규칙 위반(`critical violation`)이면 즉시 `reject`

점수 정책(예시):
- `embedding_score >= 0.88` and `rule_pass=True` -> `accept`
- `embedding_score < 0.55` or `rule_score < 0.40` -> `reject`
- 그 외 -> `review`

LLM 호출 정책(경계 구간):
- `0.65 <= embedding_score <= 0.82` 이고 치명적 규칙 위반이 없을 때만 호출
- LLM 결과는 `review` 보정용으로만 사용 (전면 자동화 금지)

### 7.1 임계값 표 (권장 초안)

| 구간/조건 | 판정 | 설명 |
|---|---|---|
| `critical_rule_fail = true` | `reject` | 하드 규칙 우선 |
| `final_score >= 0.85` and 치명 위반 없음 | `accept` | 자동 승인 구간 |
| `0.60 <= final_score < 0.85` | `review` | 수동 검토/보조판단 |
| `final_score < 0.60` | `reject` | 자동 반려 구간 |
| `0.65 <= embedding_score <= 0.82` and review 구간 | `review (+LLM)` | 경계 구간에서만 LLM 호출 |

추가 운영 규칙:
- `disclosure_requirement = "필수"`이고 `final_score >= 0.80`이면 우선 검토 순위를 높인다.
- `review`에서 LLM 재평가 후에도 `confidence < 0.75`면 `reviewing` 유지.

### 7.2 샘플 계산 5건

점수식:
`final_score = 0.50*embedding + 0.30*rule + 0.10*structure + 0.10*requirement - penalty`

| 케이스 | embedding | rule | structure | requirement | penalty | final_score | 결과 |
|---|---:|---:|---:|---:|---:|---:|---|
| A (고신뢰) | 0.92 | 0.88 | 0.90 | 1.00 | 0.00 | 0.904 | `accept` |
| B (경계+LLM) | 0.76 | 0.68 | 0.80 | 1.00 | 0.05 | 0.708 | `review` (+LLM) |
| C (낮은 점수) | 0.54 | 0.58 | 0.70 | 0.80 | 0.00 | 0.582 | `reject` |
| D (치명 위반) | 0.90 | 0.74 | 0.85 | 1.00 | 0.30 | 0.727 | `reject` (critical 우선) |
| E (중간 점수) | 0.83 | 0.79 | 0.75 | 1.00 | 0.00 | 0.815 | `review` |

해석:
- D는 수치상 review 구간이라도 치명 위반이 있으면 즉시 reject.
- E는 점수는 높지만 자동 승인 임계값(0.85) 미달이라 review로 보내 보수적으로 운영.

---

## 8. 저장 상태/전이 권장안

상태:
- `accepted`: 자동/반자동 승인
- `reviewing`: 수동 검토 필요
- `rejected`: 반려

전이:
- 초기 생성 -> `accepted | reviewing | rejected`
- `reviewing`은 운영자 승인/재평가 후 `accepted` 또는 `rejected`

권장:
- `reviewing` 큐를 반드시 운영
- 저신뢰도 자동 승격 금지

---

## 9. 품질/운영 체크포인트

1) 설명가능성(Explainability)
- `reason_codes`, `violations`, `scores`, `llm_used`를 저장

2) 재현성(Reproducibility)
- 임계값/정책 버전(`policy_version`) 기록

3) 비용 최적화
- LLM은 경계 케이스에만 호출

4) 멱등성
- 같은 입력 재실행 시 같은 결과가 나오도록 upsert key/정책 고정

5) 책임 분리
- Agent: 판단
- Tool: 계산/검증/변환
- Orchestrator: 흐름 제어
- Repository: 저장

---

## 10. 테스트 전략

단위 테스트:
- 정책 함수 입력 조합별 `accept/review/reject` 검증
- 치명 위반 우선순위 검증
- 경계 구간에서만 LLM 호출되는지 검증

통합 테스트:
- 임베딩 Tool + 규칙 Tool + Agent 정책 + Schema Mapping Tool 연결
- Orchestrator -> Repository 저장 payload shape 검증

회귀 테스트:
- 임계값 변경 시 결과 변동 폭 모니터링

---

## 11. 구현 순서 권장

1. Embedding Tool 인터페이스 고정
2. Rule Validation Tool 인터페이스 고정
3. `ucm_creation_agent` 내부 정책 모듈 구현
4. Schema Mapping Tool 구현
5. Orchestrator에서 Repository 저장 경로 연결
6. `reviewing` 운영 큐/리포트 추가

---

## 12. API 요청/응답 스키마 예시

아래 예시는 `esg_data`의 워크플로우 실행 시 정책 판단 결과를 어떻게 주고받을지에 대한 권장 포맷이다.

### 12.1 워크플로우 실행 요청 예시

```json
{
  "source_standard": "GRI",
  "target_standard": "ESRS",
  "vector_threshold": 0.7,
  "structural_threshold": 0.5,
  "final_threshold": 0.75,
  "batch_size": 40,
  "dry_run": false,
  "run_quality_check": true,
  "force_validate_only": false
}
```

### 12.2 워크플로우 응답 예시 (성공 + 품질검사 스킵)

```json
{
  "status": "success",
  "workflow": {
    "langgraph": false,
    "routed_to": "creation_agent"
  },
  "create_result": {
    "status": "success",
    "mode": "write",
    "source_standard": "GRI",
    "target_standard": "ESRS",
    "stats": {
      "processed": 40,
      "auto_confirmed_exact": 15,
      "auto_confirmed_partial": 10,
      "auto_confirmed_no_mapping": 4,
      "suggested": 6,
      "skipped_low_score": 3,
      "skipped_no_embedding": 1,
      "errors": 1
    }
  },
  "validation_result": {
    "status": "success",
    "metrics": {
      "active_data_points": 1200,
      "mapped_data_points_by_equivalent_dps": 860,
      "mapping_coverage_percent": 71.67,
      "active_unified_column_mappings": 340,
      "missing_dp_references_in_ucm": 0
    }
  },
  "quality_result": null,
  "issues": [],
  "message": "completed"
}
```

### 12.3 정책 모듈 내부 결정 결과 예시 (`DecisionResult`)

```json
{
  "decision": "review",
  "confidence": 0.74,
  "reason_codes": [
    "embedding_mid_band",
    "rule_unit_mismatch_non_critical"
  ],
  "llm_used": true,
  "evidence": {
    "embedding_score": 0.78,
    "rule_score": 0.62,
    "violations": [
      {
        "code": "unit_mismatch",
        "severity": "warning",
        "source_unit": "tCO2e",
        "target_unit": "kgCO2e"
      }
    ],
    "llm_summary": "의미는 유사하나 단위 정규화 필요"
  },
  "policy_version": "v1.0"
}
```

### 12.4 Repository upsert payload 예시 (Schema Mapping Tool 출력)

```json
{
  "unified_column_id": "UCM_ENV_0012",
  "mapped_dp_ids": [
    "gri_305_1",
    "ifrs_s2_ghg_scope1"
  ],
  "mapping_confidence": 0.91,
  "mapping_status": "accepted",
  "reason_codes": [
    "embedding_high",
    "rule_pass"
  ],
  "evidence": {
    "embedding_score": 0.93,
    "rule_score": 0.88,
    "policy_version": "v1.0"
  }
}
```

### 12.5 검증 전용 실행 예시 (`force_validate_only=true`)

```json
{
  "source_standard": "GRI",
  "target_standard": "ESRS",
  "force_validate_only": true,
  "run_quality_check": true
}
```

응답에서는 `workflow.routed_to`가 `validation_agent`로 고정되고, `create_result`는 비어 있거나 `null`일 수 있다.

---

## 13. 설정값(.env) 키 제안

아래 키들은 정책 임계값을 코드 하드코딩에서 분리하기 위한 권장안이다.

### 13.1 점수 가중치

| 키 | 기본값 | 설명 |
|---|---:|---|
| `UCM_WEIGHT_EMBEDDING` | `0.50` | 임베딩 점수 가중치 |
| `UCM_WEIGHT_RULE` | `0.30` | rulebook 정합 점수 가중치 |
| `UCM_WEIGHT_STRUCTURE` | `0.10` | 구조 정합 점수 가중치 |
| `UCM_WEIGHT_REQUIREMENT` | `0.10` | 공시 요구 강도 가중치 |

권장 검증:
- 네 가중치 합이 1.0이 아니면 런타임에 정규화하거나 부팅 시 에러 처리

### 13.2 판정 임계값

| 키 | 기본값 | 설명 |
|---|---:|---|
| `UCM_ACCEPT_THRESHOLD` | `0.85` | 자동 승인 하한 |
| `UCM_REVIEW_THRESHOLD` | `0.60` | review 하한 (`<`이면 reject) |
| `UCM_DISCLOSURE_REQUIRED_BOOST_THRESHOLD` | `0.80` | 필수 공시 우선 검토 기준 |
| `UCM_REVIEW_MIN_CONFIDENCE_AFTER_LLM` | `0.75` | LLM 후에도 이 값 미만이면 reviewing 유지 |

### 13.3 LLM 호출 제어

| 키 | 기본값 | 설명 |
|---|---:|---|
| `UCM_LLM_REVIEW_ENABLED` | `1` | 경계 구간 LLM 사용 여부 |
| `UCM_LLM_BAND_MIN` | `0.65` | LLM 보조 판단 하한 |
| `UCM_LLM_BAND_MAX` | `0.82` | LLM 보조 판단 상한 |
| `UCM_LLM_MAX_CANDIDATES_PER_DP` | `3` | DP당 LLM 재평가 후보 수 제한 |

### 13.4 페널티 값

| 키 | 기본값 | 설명 |
|---|---:|---|
| `UCM_PENALTY_CRITICAL_RULE_FAIL` | `0.30` | 치명 규칙 위반 |
| `UCM_PENALTY_DATA_TYPE_CONFLICT` | `0.20` | 타입 충돌 |
| `UCM_PENALTY_UNIT_MISMATCH` | `0.10` | 단위 불일치 |
| `UCM_PENALTY_CATEGORY_CONFLICT` | `0.10` | E/S/G 카테고리 충돌 |

### 13.5 운영 제어

| 키 | 기본값 | 설명 |
|---|---:|---|
| `UCM_REVIEW_QUEUE_ENABLED` | `1` | reviewing 큐 활성화 |
| `UCM_DRY_RUN_DEFAULT` | `0` | 기본 실행 모드 |
| `UCM_POLICY_VERSION` | `v1.0` | 판정 정책 버전 태그 |

### 13.6 `.env` 예시

```dotenv
# UCM scoring weights
UCM_WEIGHT_EMBEDDING=0.50
UCM_WEIGHT_RULE=0.30
UCM_WEIGHT_STRUCTURE=0.10
UCM_WEIGHT_REQUIREMENT=0.10

# Decision thresholds
UCM_ACCEPT_THRESHOLD=0.85
UCM_REVIEW_THRESHOLD=0.60
UCM_DISCLOSURE_REQUIRED_BOOST_THRESHOLD=0.80
UCM_REVIEW_MIN_CONFIDENCE_AFTER_LLM=0.75

# LLM review band
UCM_LLM_REVIEW_ENABLED=1
UCM_LLM_BAND_MIN=0.65
UCM_LLM_BAND_MAX=0.82
UCM_LLM_MAX_CANDIDATES_PER_DP=3

# Penalties
UCM_PENALTY_CRITICAL_RULE_FAIL=0.30
UCM_PENALTY_DATA_TYPE_CONFLICT=0.20
UCM_PENALTY_UNIT_MISMATCH=0.10
UCM_PENALTY_CATEGORY_CONFLICT=0.10

# Ops
UCM_REVIEW_QUEUE_ENABLED=1
UCM_DRY_RUN_DEFAULT=0
UCM_POLICY_VERSION=v1.0
```

---

**문서 상태**: Draft  
**범위**: `esg_data` UCM 생성 파이프라인 (Phase 3+)  
