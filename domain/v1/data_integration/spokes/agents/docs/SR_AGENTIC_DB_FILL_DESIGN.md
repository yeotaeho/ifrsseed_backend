# SR 에이전트: DB 4개 테이블 채우기 설계 문서

지속가능경영보고서(SR) PDF를 검색·다운로드한 뒤,  
`historical_sr_reports`, `sr_report_index`, `sr_report_body`, `sr_report_images` 4개 테이블에 값을 채우는 방식을 두 가지로 정리한 문서입니다.

- **방법 A**: 완전 에이전틱 — LLM이 PDF 내용을 해석하고 도구만으로 4개 테이블 채우기  
- **방법 B**: 하이브리드 — PyMuPDF로 추출 후, 백엔드/도구로 DB 저장

### 구현 상태 (방법 B-1)

- **에이전트**: `sr_agent.py` — OpenAI `gpt-5-mini` + `OPENAI_API_KEY` 사용.
- **방법 B-1** 적용: 파싱은 PyMuPDF(`sr_report_tools`)로 수행한 뒤, `SRParsingResultRepository`가 4개 테이블에 저장.
- **방법 A** 구현: `use_docling_llm=True` 시 Docling 파싱 + `SRSaveAgent`(LLM/도구 기반 저장).
- **LangGraph 토폴로지**: `hub/orchestrator/sr_workflow.py` — StateGraph `fetch_and_parse` → (조건) → `save` → END. 상태는 `models/langgraph/sr_workflow_state.SRWorkflowState`.
- **관련 코드**:
  - 방법 B-1: `hub/repositories/sr_parsing_result_repository.py` (`SRParsingResultRepository.save_parsing_result()`)
  - 방법 A: `domain/shared/tool/sr_report_tools_docling.py`, `domain/shared/tool/sr_save_tools.py`, `spokes/agents/sr_save_agent.py`
  - `hub/orchestrator/sr_orchestrator.py`: LangGraph 그래프 호출 (실패 시 기존 순차 실행 fallback)
  - ORM: `models/bases/sr_report_index.py`, `sr_report_body.py`, `sr_report_images.py`

---

## 공통 전제

- **DB 권한**: 모델에 raw SQL/DB 접속을 주지 않고, 백엔드가 구현한 **도구(Tool)**만 노출한다.  
  각 도구는 파라미터 검증 후 INSERT를 수행하며, 이 권한 범위 내에서만 "DB 접근"이 허용된다.
- **대상 테이블**:  
  `historical_sr_reports` → `sr_report_index`, `sr_report_body`, `sr_report_images` (report_id FK).

---

## 방법 A: 완전 에이전틱 (Full Agentic)

### 개요

- LLM(예: GPT-5)에게 **PDF 내용**(텍스트 추출본 또는 페이지 이미지)을 컨텍스트로 제공한다.
- **도구**: `save_historical_sr_report`, `save_sr_report_index`, `save_sr_report_body`, `save_sr_report_image` 를 노출한다.
- **프롬프트**: “제공된 PDF 내용을 보고, 아래 도구만 사용해 4개 테이블을 채우시오. 먼저 메타데이터를 저장하고, 반환된 report_id로 나머지 테이블을 채우시오.” 같은 **단계별 지시**를 준다.
- 모델이 스스로 메타·인덱스·본문·이미지를 해석하고, 위 도구를 여러 번 호출해 4개 테이블을 채운다.

### 흐름

```
[PDF bytes] → (텍스트/이미지 추출) → [LLM 컨텍스트]
                    ↓
[시스템 프롬프트 + 사용자 프롬프트]
  - "PDF 내용을 보고 save_* 도구로 4개 테이블 채우기"
  - 1단계: save_historical_sr_report → report_id 획득
  - 2단계: save_sr_report_index (여러 행)
  - 3단계: save_sr_report_body (페이지별)
  - 4단계: save_sr_report_image (선택)
                    ↓
[에이전트 루프] LLM이 도구 호출 반복 → 백엔드가 검증 후 INSERT
                    ↓
[완료] 4개 테이블 채워진 상태
```

### 도구 스펙 (방법 A)

백엔드가 구현해 LLM에 바인딩하는 도구 예시이다.  
실제 컬럼명/타입은 `012_drop_old_add_sr_report_tables.py` 및 ORM과 맞춘다.

| 도구명 | 설명 | 주요 인자 (예시) | 반환 |
|--------|------|------------------|------|
| `save_historical_sr_report` | 보고서 메타 1건 INSERT | company_id, report_year, report_name, source, total_pages, index_page_numbers | report_id (UUID) |
| `save_sr_report_index` | 인덱스 행 1건 INSERT | report_id, index_type, index_page_number, dp_id, dp_name, page_numbers, section_title, remarks | id (UUID) |
| `save_sr_report_body` | 본문 행 1건 INSERT | report_id, page_number, is_index_page, content_text, content_type, paragraphs(JSON) | id (UUID) |
| `save_sr_report_image` | 이미지 행 1건 INSERT | report_id, page_number, image_index, image_type, caption_text, ... | id (UUID) |

- `report_id`는 반드시 `save_historical_sr_report` 반환값을 사용하도록 프롬프트에 명시한다.

### 프롬프트 설계 (방법 A)

- **시스템 프롬프트**:  
  - 역할: “지속가능경영보고서 PDF 내용을 분석해, 제공된 도구만 사용해 DB 4개 테이블을 채우는 에이전트.”  
  - 규칙: 한 번에 하나의 도구만 호출; 도구 결과를 확인한 뒤 다음 도구 호출; report_id는 첫 번째 도구 반환값을 사용.
- **사용자(작업) 프롬프트**:  
  - “아래는 [회사명] [연도] SR 보고서 PDF에서 추출한 내용이다. 다음 순서로 도구를 사용해 테이블을 채우시오.  
    1) 메타데이터를 추출해 save_historical_sr_report를 한 번 호출하고 report_id를 기억하시오.  
    2) 인덱스 페이지(목차/DP 매핑)에서 각 DP별로 save_sr_report_index(report_id, ...)를 호출하시오.  
    3) 각 본문 페이지에 대해 save_sr_report_body(report_id, page_number, content_text, ...)를 호출하시오.  
    4) (선택) 이미지가 있으면 save_sr_report_image(...)를 호출하시오.  
    모든 행을 처리했으면 완료 메시지를 반환하시오.”

### 장단점 (방법 A)

| 장점 | 단점 |
|------|------|
| 하나의 프롬프트로 “도구만 써서 4개 테이블 채우기” 가능 | 도구 호출 횟수 많음 (본문 페이지 수만큼 등) |
| PDF 구조 해석을 모델에 맡길 수 있음 | 형식 오류·환각 가능성, 타입/제약 위반 시 재시도 필요 |
| 고급 모델이면 지시 이해도 좋음 | 긴 보고서는 컨텍스트/토큰·비용 이슈 (청킹 또는 요약 필요) |

### 구현 시 고려사항 (방법 A)

- **PDF → LLM 입력**:  
  - 텍스트: PyMuPDF 등으로 페이지별 텍스트 추출 후 문자열로 컨텍스트에 포함 (또는 청킹).  
  - 이미지: 페이지를 이미지로 렌더링해 비전 모델에 넘기는 방식 가능 (토큰/비용 큼).
- **에이전트 루프**:  
  - LangChain/LangGraph 등으로 도구 바인딩 + ReAct/plan-and-execute 스타일 루프.  
  - 최대 스텝 제한, 실패 시 재시도/롤백 정책 필요.
- **보안**:  
  - 도구는 INSERT만 허용하고, 파라미터는 서버에서 타입·FK·길이 검증 후 사용.

---

## 방법 B: 하이브리드 (Hybrid)

### 개요

- **추출(파싱)** 은 기존처럼 **PyMuPDF 기반** `sr_report_tools`  
  (`parse_sr_report_metadata`, `parse_sr_report_index`, `parse_sr_report_body`, `parse_sr_report_images`) 로 수행한다.
- **채우기** 는 두 가지 중 택일 또는 병행 가능:  
  - **B-1**: 파싱 결과(`SRParsingResult`)를 그대로 **기존 리포지토리/서비스**로 DB INSERT (도구 없음).  
  - **B-2**: 파싱 결과를 LLM에게 주고, “이 구조를 검증/보정한 뒤 저장 도구를 이렇게 호출하라”는 식으로 **검증·보정용 에이전트**만 두고, 실제 INSERT는 백엔드 도구 또는 리포지토리로 수행.

즉, “프롬프트로 tool 활용해 4개 테이블에 값을 채우시오”를 **의미적으로** 만족하면서, 추출 정확도와 비용은 기존 파이프라인을 유지하는 방식이다.

### 흐름 (B-1: 도구 없이 저장)

```
[PDF bytes] → _parse_all_tables() (PyMuPDF)
                    ↓
              SRParsingResult
  (historical_sr_reports, sr_report_index, sr_report_body, sr_report_images)
                    ↓
[기존] HistoricalSRReportRepository + index/body/images 저장 로직
                    ↓
[완료] 4개 테이블 채워진 상태
```

- `sr_agent.py`의 `_parse_all_tables()`와 동일한 흐름이며, “에이전트가 도구로 채운다”는 표현은 **내부적으로 파싱 결과를 한 번에 저장하는 서비스/오케스트레이터**가 “채우기” 역할을 한다고 보면 된다.

### 흐름 (B-2: 검증·보정 에이전트 + 저장 도구)

```
[PDF bytes] → _parse_all_tables() (PyMuPDF)
                    ↓
              SRParsingResult (JSON 또는 요약)
                    ↓
[LLM] 프롬프트: "아래 파싱 결과를 검증하고, 오류/빈값이 있으면 보정 제안을 하고,
       save_* 도구 호출 계획(또는 호출)을 제시하시오."
       도구: save_historical_sr_report, save_sr_report_index, save_sr_report_body, save_sr_report_image
                    ↓
[옵션 1] LLM이 도구 호출 → 백엔드가 INSERT
[옵션 2] LLM이 보정된 JSON만 반환 → 백엔드가 한 번에 INSERT (도구는 검증/시뮬레이션용)
                    ↓
[완료] 4개 테이블 채워진 상태
```

- B-2는 “도구를 활용해 채우기”를 **검증·보정 단계**에 두고, 실제 대량 INSERT는 백엔드가 수행하는 형태다.

### 도구 스펙 (방법 B)

- **B-1**: 기존 `HistoricalSRReportRepository` 및 index/body/images용 저장 로직을 그대로 사용. 별도 “DB 쓰기 도구”는 없음.
- **B-2**: 방법 A와 동일한 `save_*` 도구를 노출할 수 있되,  
  - 호출 주체가 “파싱 결과를 검증·보정한 LLM”이고,  
  - 입력이 “이미 구조화된 SRParsingResult”이므로 호출 횟수와 오류 가능성을 줄일 수 있다.  
  또는 **한 건씩 INSERT하는 대신** `save_parsing_result_batch(historical_sr_reports, sr_report_index, sr_report_body, sr_report_images)` 같은 **배치 도구** 하나만 두고, LLM은 “이 JSON을 그대로 저장하라”는 단일 호출만 하게 할 수 있다.

### 프롬프트 설계 (방법 B)

- **B-1**: 에이전트용 프롬프트 없음. 기존 오케스트레이터/서비스의 “파싱 결과 저장” 로직만 사용.
- **B-2**:  
  - 시스템: “SR 파싱 결과(historical_sr_reports, sr_report_index, sr_report_body, sr_report_images)를 검증하고, 필요 시 보정한 뒤, 제공된 저장 도구로 DB에 반영하는 에이전트.”  
  - 사용자: “아래는 [회사명] [연도] SR PDF의 파싱 결과이다. 필수 필드·타입·report_id 일관성을 검증하고, 문제가 있으면 보정한 뒤 save_* 도구(또는 save_parsing_result_batch)를 호출하시오.”

### 장단점 (방법 B)

| 장점 | 단점 |
|------|------|
| 추출 품질이 PyMuPDF로 일정함 | “완전히 프롬프트만으로 채우기”는 아님 (B-1은 도구 없음) |
| 토큰·비용·호출 횟수 절감 (B-1은 LLM 없이 저장) | B-2는 방법 A보다는 단순하지만, 검증/보정 로직 설계 필요 |
| 기존 코드 재사용 가능 | B-2에서 배치 도구를 쓸 경우, “행 단위 도구” 대신 “한 번에 채우기”에 가까움 |

### 구현 시 고려사항 (방법 B)

- **B-1**: `sr_agent.py`의 `execute()` → `_parse_all_tables()` → 반환된 `parsing_result`를 `sr_orchestrator` 또는 전용 서비스에서 `HistoricalSRReportRepository` 등으로 저장하는 흐름을 유지/정리.
- **B-2**:  
  - 파싱 결과를 JSON으로 LLM 컨텍스트에 넣을 때, 본문 텍스트가 길면 요약하거나 청킹해 토큰 제한을 넘지 않도록 한다.  
  - 배치 도구 사용 시, 트랜잭션(전부 성공 시 커밋, 실패 시 롤백)을 백엔드에서 처리한다.

---

## 비교 요약

| 항목 | 방법 A (완전 에이전틱) | 방법 B (하이브리드) |
|------|------------------------|----------------------|
| PDF 해석 | LLM이 PDF 내용 직접 해석 | PyMuPDF로 추출 |
| 4개 테이블 채우기 | LLM이 save_* 도구 반복 호출 | B-1: 리포지토리로 일괄 저장 / B-2: 검증·보정 후 도구 또는 배치 저장 |
| 프롬프트 역할 | “도구만 써서 4개 테이블 채우시오” (단계별 지시) | B-1: 없음 / B-2: “파싱 결과 검증·보정 후 저장 도구 사용” |
| 토큰·비용 | 높음 (긴 PDF 전체 또는 이미지) | B-1: 저장 구간 LLM 없음 / B-2: 중간 (구조화된 JSON 위주) |
| 안정성 | 형식 오류·환각 가능성 있음 | PyMuPDF 기반으로 안정적 |
| 구현 난이도 | 도구 4개 + 에이전트 루프 + 프롬프트 설계 | B-1: 기존 유지 / B-2: 검증 에이전트 + 배치 도구 선택 |

---

## 참고: 테이블 구조 (요약)

- **historical_sr_reports**: id, company_id, report_year, report_name, pdf_file_path, source, total_pages, index_page_numbers, created_at  
- **sr_report_index**: id, report_id(FK), index_type, index_page_number, dp_id, dp_name, page_numbers(ARRAY), section_title, remarks, parsed_at, parsing_method, confidence_score  
- **sr_report_body**: id, report_id(FK), page_number, is_index_page, content_text, content_type, paragraphs(JSONB), embedding_id, embedding_status, parsed_at  
- **sr_report_images**: id, report_id(FK), page_number, image_index, image_width, image_height, image_type, caption_text, caption_confidence, extracted_data(JSONB), caption_embedding_id, embedding_status, extracted_at (선택 `image_blob`)  

상세 스키마는 `backend/alembic/versions/012_drop_old_add_sr_report_tables.py` 및 ORM 모델을 참고한다.
