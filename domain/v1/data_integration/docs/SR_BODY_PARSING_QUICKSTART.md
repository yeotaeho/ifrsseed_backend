# SR 본문 파싱·저장 구현 가이드 (Quick Start)

> **전체 설계**: [`SR_BODY_PARSING_DESIGN.md`](./SR_BODY_PARSING_DESIGN.md) 참조

## 개요

SR 보고서 PDF → 페이지별 텍스트 추출 → `sr_report_body` 테이블 저장

**현재 상태**: 매핑·저장 도구 ✅ / **통합 파싱(`body_parser.py`: Docling→LlamaParse→PyMuPDF)** ✅ / **API `POST /data-integration/sr-agent/extract-and-save/body-agentic`** ✅

---

## 빠른 실행

### 1. 파싱 도구 (구현됨)

**파일**: `backend/domain/shared/tool/parsing/body_parser.py`

- `parse_body_pages(pdf_bytes_b64, pages)` → Docling(페이지별 슬라이스) → LlamaParse → PyMuPDF
- 환경변수: `SR_BODY_SKIP_DOCLING=1`(Docling 생략), `SR_BODY_DOCLING_MAX_WORKERS`(기본 2)
- 목차(`toc_path`) 진단 로그: `SR_BODY_TOC_DEBUG=1` — 페이지 상단 제목 추출 결과(본문 페이지 수, 채워진 수, null 수) 출력

### 2. MCP 도구 (연결됨)

**파일**: `backend/domain/v1/data_integration/spokes/infra/sr_body_tools_server.py` — `parse_body_pages_tool`이 위 `body_parser.parse_body_pages`를 호출합니다. 인프로세스 MCP는 `mcp_client.py` 동일.

### 3. API 호출

**에이전트 직행(설계 §6.4, `report_id` + 선택 `pdf_bytes_b64`)**:

```bash
curl -X POST http://localhost:8000/data-integration/sr-agent/extract-and-save/body-agentic \
  -H "Content-Type: application/json" \
  -d "{\"report_id\": \"<uuid>\", \"pdf_bytes_b64\": null}"
```

`pdf_bytes_b64`가 없으면 **400** — DB에 PDF 로컬 경로 컬럼은 없습니다. `body-agentic` 호출 시 **base64 PDF를 넣으세요.**

**LangGraph + SRAgent fetch(권장, `pdf_bytes_b64` 불필요)**  
`report_id`가 있으면 워크플로가 **메타데이터 INSERT를 건너뛰고**, 검색·다운로드한 PDF로 바로 본문 저장합니다.

```bash
curl -X POST http://localhost:8000/data-integration/sr-agent/extract-and-save/body \
  -H "Content-Type: application/json" \
  -d "{\"company\": \"...\", \"year\": 2024, \"report_id\": \"<기존-uuid>\"}"
```

**응답 진단 필드** (`ExtractAndSaveBodyResponse`):

| 필드 | 설명 |
|------|------|
| `success` | `fetch_success`이고 이번 요청에서 `saved_count > 0` (본문 엔드포인트) |
| `message` | fetch + 본문 요약 문장 |
| `saved_count` | 이번 실행에서 저장된 행 수 |
| `errors` | `SRBodyAgent`가 반환한 오류 목록(가능하면 채움) |
| `fetch_success` / `fetch_message` | **body** 엔드포인트만: SRAgent PDF 단계 |
| `body_agent_success` / `body_agent_message` | 에이전트가 반환한 success/message |
| `db_sr_report_body_row_count` | 요청 종료 시점 DB `sr_report_body` 행 수(해당 `report_id`) |

---

## 핵심 플로우

```
get_pdf_metadata (total_pages, index_page_numbers)
    ↓
parse_body_pages (Docling/LlamaParse)
    ↓
map_body_pages_to_sr_report_body (is_index_page 세팅)
    ↓
save_sr_report_body_batch (DB INSERT)
```

---

## 체크리스트

### Phase 1 (필수)
- [x] `body_parser.py` 구현
- [x] MCP 도구 연결 (`sr_body_tools_server`, in-process `mcp_client`)
- [x] API `extract-and-save/body-agentic` 추가
- [x] 단위 테스트 `tests/test_body_parser.py` (pytest 환경에서 실행)
- [ ] E2E(실제 SR PDF + DB) 통합 테스트

### Phase 2 (선택)
- [ ] 문단 분할 (`paragraphs`)
- [ ] 콘텐츠 타입 분류 (`content_type`)
- [ ] 임베딩 생성

---

## 참고

**인덱스와의 연결**:
```sql
-- DP → 본문 문단 검색
SELECT b.content_text 
FROM sr_report_index i
JOIN sr_report_body b ON b.page_number = ANY(i.page_numbers)
WHERE i.dp_id = 'GRI-305-1'
```

**기존 도구** (이미 완성):
- `map_body_pages_to_sr_report_body` — `sr_body_mapping.py`
- `save_sr_report_body_batch` — `sr_save_tools.py`
- `SRBodyAgent` — `sr_body_agent.py`

**이미지(`sr_report_images`) 파이프라인 설계**: [`SR_IMAGES_PARSING_DESIGN.md`](./SR_IMAGES_PARSING_DESIGN.md)  
**이미지 에이전트 API**: `POST .../extract-and-save/images-agentic` (`SR_IMAGE_OUTPUT_DIR` 또는 요청 `image_output_dir`)  
**이미지 MCP**: `sr_images_tools` — `spokes/infra/sr_images_tools_server.py`, 원격 시 `MCP_SR_IMAGES_TOOLS_URL`

---

**예상 소요**: 파싱 도구 1일 + 테스트 1일 = **총 2일**
