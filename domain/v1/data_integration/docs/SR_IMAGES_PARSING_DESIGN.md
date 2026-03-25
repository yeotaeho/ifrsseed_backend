# SR 이미지(`sr_report_images`) 파싱·저장 설계 및 구현 가이드

## 문서 개요

**목적**: SR 보고서 PDF에서 이미지를 추출·메타데이터화하여 `sr_report_images` 테이블(및 파일 스토리지)에 저장하는 전체 플로우를 **현재 코드베이스 구조**(인덱스·본문과 동일한 패턴)에 맞게 설계합니다.

**참고 문서**

| 문서 | 활용 |
|------|------|
| [SR_BODY_PARSING_DESIGN.md](./SR_BODY_PARSING_DESIGN.md) | 에이전트·MCP·워크플로 노드·저장 툴 패턴 |
| [SR_BODY_PARSING_QUICKSTART.md](./SR_BODY_PARSING_QUICKSTART.md) | API·환경변수·체크리스트 스타일 |
| [DATABASE_TABLES_STRUCTURE.md](../../ifrs_agent/docs/DATABASE_TABLES_STRUCTURE.md) | `sr_report_images` 스키마·인덱스 |
| [HISTORICAL_REPORT_PARSING.md](../../ifrs_agent/docs/HISTORICAL_REPORT_PARSING.md) | 전체 SR 파싱 플로우·RAG에서 이미지 활용 |
| [SR_IMAGES_MEMORY_BLOB_OBJECT_STORAGE.md](./SR_IMAGES_MEMORY_BLOB_OBJECT_STORAGE.md) | 디스크 없이 메모리/BYTEA/S3로 전환하는 **구현 단계별 가이드** |
| [SR_IMAGES_VLM_ENRICHMENT.md](./SR_IMAGES_VLM_ENRICHMENT.md) | VLM으로 `image_type`·`caption_text`·`caption_confidence` 보강 — **설계 vs 구현 단계** |

**현재 구현 상태 (요약)**

| 구성요소 | 상태 |
|----------|------|
| DB 테이블 `sr_report_images` | ✅ Alembic·ORM (`SrReportImage`) 존재 |
| 저장 툴 `save_sr_report_image` | ✅ 단건 INSERT (`sr_save_tools.py`) |
| `save_sr_report_images_batch` | ❌ 없음 (본문은 `save_sr_report_body_batch` 있음) |
| `SRImagesAgent` | ⚠️ **스텁** (`saved_count=0`) |
| LangGraph `sr_workflow` `save_images` 노드 | ✅ `AgentRouter` → `sr_images_agent` 연결됨 |
| 공유 파싱 모듈 (PDF→이미지 파일) | ⚠️ 문서 `PDF_PARSING_IN_MEMORY.md`에 `parse_sr_report_images` 언급 있으나, **`sr_report_tools`에 해당 심볼이 없을 수 있음** — 별도 구현 필요 |

---

## 1. 배경 및 목표

### 1.1 비즈니스 목표

1. **DP/페이지 기반 RAG 보강**: `sr_report_index.page_numbers`로 본문(`sr_report_body`)을 찾은 뒤, **같은 `report_id` + `page_number`의 이미지**를 FactSheet에 포함 ([HISTORICAL_REPORT_PARSING.md](../../ifrs_agent/docs/HISTORICAL_REPORT_PARSING.md) Phase 2-5).
2. **차트·그래프 검색**: 캡션·타입·(선택) 구조화 `extracted_data`로 멀티모달/텍스트 검색 확장.
3. **인덱스·본문과 동일한 운영 패턴**: `report_id` + PDF bytes(또는 경로) → 파싱 → 매핑 → 배치 저장.

### 1.2 설계 원칙 (본문 파이프라인과 정렬)

- **에이전트는 LLM 없이 결정적 파이프라인 우선** (`SRBodyAgent`와 동일 철학): 대용량 PDF에서 불필요한 토큰 사용 방지.
- **저장 진입점**: 워크플로 노드에서 에이전트 호출 후, 실제 INSERT는 **`sr_save_tools`**(또는 repository)로 통일하는 것이 바람직.
- **파일은 디스크(추출 파이프라인), DB에는 경로 미저장**: 임베디드 이미지는 `output_dir`에만 쓰고, `sr_report_images`에는 크기·캡션·메타만 저장.

### 1.3 제약·주의

- **용량**: 보고서당 이미지 수·해상도에 따라 디스크·DB 부하 큼 → 페이지 배치·동시성 상한·최대 픽셀 정책 필요.
- **저작권/PII**: 추출 이미지에 민감 정보가 있을 수 있음 → 보관 경로·접근 권한 정책 명시.
- **인덱스 페이지**: 본문과 같이 `index_page_numbers`에 해당하는 페이지의 이미지는 **저장 제외**할지 정책 결정 (기본 제안: **제외**, 목차·네비 캡처 노이즈 감소).

---

## 2. 데이터 스키마 (`sr_report_images`)

[DATABASE_TABLES_STRUCTURE.md](../../ifrs_agent/docs/DATABASE_TABLES_STRUCTURE.md)와 ORM `backend/domain/v1/data_integration/models/bases/sr_report_images.py` 기준.

| 컬럼 | 용도 |
|------|------|
| `id` | PK (UUID) |
| `report_id` | FK → `historical_sr_reports.id` |
| `page_number` | 1-based 페이지 |
| `image_index` | 페이지 내 순서 (0-based 권장) |
| *(제거됨)* | `image_file_path` 컬럼은 스키마에서 제거됨 |
| *(제거됨)* | `image_file_size` 컬럼 제거(Alembic `018_drop_sr_image_file_size`) — 크기는 `extracted_data.size_bytes` 또는 `image_blob` 길이 |
| `image_width`, `image_height` | 메타 |
| `image_type` | `chart` / `graph` / `photo` / `diagram` / `table` / `unknown` |
| `caption_text`, `caption_confidence` | 캡션(후속 LLM/Vision) |
| `extracted_data` | JSONB (차트 수치 등, 후속) |
| `caption_embedding_id`, `embedding_status` | 벡터 검색 연동 |
| `extracted_at` | 타임스탬프 |

**유일성**: 현재 DB에 `(report_id, page_number, image_index)` UNIQUE가 없다면, **재실행 시 중복 행**이 쌓일 수 있음 → 구현 단계에서 **삭제 후 삽입** 또는 **UNIQUE + upsert** 전략을 문서화·적용할 것 (제안은 §6).

**JOIN 예시 (본문·인덱스와 함께)**

```sql
-- 특정 DP가 가리키는 페이지의 이미지
SELECT img.*
FROM sr_report_index i
JOIN sr_report_images img
  ON img.report_id = i.report_id
 AND img.page_number = ANY(i.page_numbers)
WHERE i.report_id = :report_id
  AND i.dp_id = :dp_id;
```

---

## 3. 아키텍처 (현재 구조에 맞춘 계층)

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: 메타데이터 준비 (기존과 동일)                        │
└─────────────────────────────────────────────────────────────┘
[1] get_pdf_metadata / state: total_pages, index_page_numbers, report_id

┌─────────────────────────────────────────────────────────────┐
│ Phase 2: PDF → 이미지 바이너리 추출 + 파일 쓰기               │
└─────────────────────────────────────────────────────────────┘
[2] extract_report_images(pdf_bytes, pages, output_dir, base_name, ...)
    → { page_number: [ { "path", "width", "height", "size_bytes", "image_index" }, ... ] }
    구현 후보: PyMuPDF(빠름) 우선, 필요 시 Docling 이미지 아티팩트 보조

┌─────────────────────────────────────────────────────────────┐
│ Phase 3: 도메인 매핑 (얇은 레이어)                            │
└─────────────────────────────────────────────────────────────┘
[3] map_extracted_images_to_sr_report_rows(report_id, extracted_by_page)
    → sr_report_images INSERT용 dict 리스트 (DB id는 저장 시 생성)

┌─────────────────────────────────────────────────────────────┐
│ Phase 4: 배치 저장                                            │
└─────────────────────────────────────────────────────────────┘
[4] save_sr_report_images_batch(report_id, rows)
    → 단일 트랜잭션 권장, per-row errors 수집 (본문 batch 패턴과 동일)

┌─────────────────────────────────────────────────────────────┐
│ Phase 5: 에이전트 (SRImagesAgent)                             │
└─────────────────────────────────────────────────────────────┘
[5] execute(): 메타 조회(선택) → [2]→[3]→[4]
    SRBodyAgent와 같이 asyncio.to_thread로 CPU/IO 블로킹 분리
```

**배치 위치 제안**

| 레이어 | 경로 제안 |
|--------|-----------|
| 파싱 (추출) | `backend/domain/shared/tool/parsing/image_extractor.py` (신규) |
| 매핑 | `backend/domain/shared/tool/sr_report/images/sr_image_mapping.py` (신규, `body` 패키지와 대칭) |
| 저장 | `sr_save_tools.save_sr_report_images_batch` (신규) |
| 에이전트 | `sr_images_agent.py` (기존 스텁 확장) |
| MCP | `spokes/infra/sr_images_tools_server.py` + `mcp_client` 의 `sr_images_tools` (인프로세스/stdio·HTTP URL `MCP_SR_IMAGES_TOOLS_URL`) |

워크플로 **`sr_workflow._save_images_node`**는 이미 `sr_images_agent`를 호출하므로, **에이전트만 완성하면 파이프라인 끝이 연결**됩니다.

---

## 4. 파싱(추출) 전략

### 4.1 1차: PyMuPDF (`fitz`)

- **장점**: 로컬·빠름·페이지 단위 제어 쉬움. `page.get_images()` → xref로 픽스맵 추출.
- **산출물**: PNG/WebP 등으로 `image_output_dir`에 저장 (본문과 동일하게 bytes 입력 시 **출력 디렉터리 필수**).
- **필터**: 너무 작은 썸네일(아이콘)·투명 1×1 등 휴리스틱 제거.

### 4.2 2차(선택): Docling

- 레이아웃 기반 figure와 연결해 **캡션 후보 텍스트**를 얻는 데 유리할 수 있음.
- 단, 파이프라인 복잡도·의존성 증가 → **Phase 2 이후**로 미루는 것을 권장.

### 4.3 페이지 범위

- **전 페이지 순회** vs **본문만**: 기본은 `1..total_pages`에서 `index_page_numbers` 제외.
- 대용량 보고서는 **청크 단위 페이지 리스트**로 반복 호출해 메모리 폭주 방지.

---

## 5. 매핑·저장 계약

### 5.1 행 dict 최소 필드 (배치 저장 입력)

`save_sr_report_body_batch`와 유사하게 다음을 권장합니다.

```python
{
    "page_number": int,
    "image_index": int,
    # image_file_path / image_file_size 컬럼 없음 — 크기는 extracted_data.size_bytes 등
    "image_width": int | None,
    "image_height": int | None,
    "image_type": str | None,       # Phase 1에서는 None 또는 휴리스틱
    "caption_text": str | None,     # Phase 1 None
    "caption_confidence": float | None,
    "extracted_data": dict | None,
}
```

`id`, `extracted_at`, `embedding_status`는 DB 기본값·저장 툴에서 설정.

### 5.2 파일 경로 규칙 (제안)

- `{image_output_dir}/{report_id_short}/{page_number}_{image_index}.{ext}`
- 또는 `{base_name}_p{page}_{idx}.{ext}` ([PDF_PARSING_IN_MEMORY.md](./PDF_PARSING_IN_MEMORY.md) 스타일과 호환)
- **다중 서버/컨테이너**에서는 NFS 또는 S3 등 객체 스토리지 + `extracted_data` 등 메타에 참조 정책을 문서화.

---

## 6. 재실행·멱등성 (제안)

- **옵션 A**: 동일 `report_id` 이미지 저장 전 `DELETE FROM sr_report_images WHERE report_id = ?` 후 배치 INSERT (구현 단순).
- **옵션 B**: `(report_id, page_number, image_index)` UNIQUE + upsert (Alembic 마이그레이션 필요).
- 파일 시스템은 A 선택 시 **기존 디렉터리 비우기** 또는 UUID 파일명으로 충돌 방지.

---

## 7. 단계별 구현 로드맵

### Phase 0 — 정리 (0.5일)

- [x] `PDF_PARSING_IN_MEMORY.md`: `parse_sr_report_images` → `extract_report_images` 및 설계 문서 링크로 정리.
- [x] `image_output_dir` 정책: 환경변수 `SR_IMAGE_OUTPUT_DIR` 또는 API/LangGraph state `image_output_dir` (없으면 에이전트 명시 실패).

### Phase 1 — 최소 기능 (MVP, 2~4일)

1. [x] `image_extractor.py`: `pdf_bytes` + `pages` → 파일 저장 + 메타 리스트.
2. [x] `sr_image_mapping.py`: 추출 결과 → 저장용 dict 리스트.
3. [x] `save_sr_report_images_batch` in `sr_save_tools.py` (에이전트·배치 경로에서 직접 호출; `SR_SAVE_TOOLS` 리스트는 단건 `save_sr_report_image` 유지).
4. [x] `SRImagesAgent.execute` 구현: `get_pdf_metadata` → `extract_report_images` → `map_extracted_images_to_sr_report_rows` → `save_sr_report_images_batch`.
5. [x] 단위 테스트: `test_image_extractor.py`, `test_sr_image_mapping.py`.
6. [ ] 수동: LangGraph 전체 플로우에서 `images_saved_count` > 0 확인 (`SR_IMAGE_OUTPUT_DIR` 설정 필요).

### Phase 2 — 운영 품질 (2~3일)

- [x] 썸네일/아이콘 필터(기존 `SR_IMAGE_MIN_EDGE` / `SR_IMAGE_MIN_BYTES`), 최대 해상도 리사이즈 `SR_IMAGE_MAX_EDGE`(0=비활성).
- [x] 진행 로그 (`SR_IMAGE_DEBUG=1`).
- [x] `sr_report_images_repository.count_sr_report_images_rows` — 워크플로 `save_images` 노드·API 응답(`db_sr_report_images_row_count`).

### Phase 3 — 캡션·분류·구조화 (선택, 별도 스프린트)

- [ ] `image_type` 휴리스틱 또는 소형 분류 모델.
- [ ] 캡션: 근접 텍스트 블록(PyMuPDF 텍스트 bbox) 또는 Vision API.
- [ ] `extracted_data`: 차트 전용 파서(별도 설계).

### Phase 4 — MCP·API 대칭 (선택)

- [x] MCP `sr_images_tools`: `extract_report_images_tool`, `map_extracted_images_to_sr_report_rows_tool`, `save_sr_report_images_batch_tool`, `get_pdf_metadata_tool` (`sr_images_tools_server.py`, `mcp_client.load_inprocess_tools("sr_images_tools")`).
- [x] `sr_agent_router`에 `POST .../extract-and-save/images-agentic` (본문 `body-agentic` 미러). LangGraph `extract-and-save/images`에 `image_output_dir`·진단 필드 확장.

---

## 8. 테스트 전략

| 레벨 | 내용 |
|------|------|
| 단위 | 추출 함수: 가짜 PDF 또는 최소 PDF fixture, 이미지 xref 1개 이상 |
| 단위 | 매핑: 경로·인덱스·페이지 번호 일관성 |
| 단위 | 저장 batch: DB mock 또는 테스트 DB 트랜잭션 롤백 |
| 통합 | `SRImagesAgent` + 실제 `save_sr_report_images_batch` (개발 DB) |
| 회귀 | `python -m pytest backend/domain/v1/data_integration/tests` + 이미지 전용 `test_sr_images_*.py` 추가 |

---

## 9. 추가 제안 (결정 사항으로 남길 항목)

1. **객체 스토리지 전환**: 온프레미스 디스크 대신 MinIO/S3를 쓰면 메타/URL은 `extracted_data` 등으로 정책을 문서화.
2. **본문 마크다운의 `<!-- image -->`와의 관계**: LlamaParse 본문에 플레이스홀더만 있고 실제 바이너리는 PDF에서만 나오는 경우가 많음 → **이미지는 PDF xref 추출이 정답에 가깝다**는 전제를 RAG 설계에 명시.
3. **중복 이미지**: 동일 xref가 여러 페이지에 참조될 수 있음 → `image_index`를 페이지 로컬로 두고, 필요 시 `source_xref` 같은 컬럼을 향후 추가하는 스키마 확장 검토.
4. **보안**: 업로드 PDF 악성 여부 스캔, 추출 파일 실행 금지(확장자·MIME 고정).
5. **워크플로만 이미지 실행**: `only_step=images` + 기존 `report_id`일 때 `pdf_bytes`가 state에 없으면 **DB에서 PDF 로드** (본문 `_resolve_pdf_bytes`와 동일 패턴) — `sr_workflow`/`AgentRouter`에 보강 제안.

---

## 10. 참고 코드 위치 (현재)

- 에이전트 스텁: `backend/domain/v1/data_integration/spokes/agents/sr_images_agent.py`
- 단건 저장 툴: `backend/domain/shared/tool/sr_report/save/sr_save_tools.py` (`save_sr_report_image`)
- 워크플로 노드: `backend/domain/v1/data_integration/hub/orchestrator/sr_workflow.py` (`_save_images_node`)
- ORM: `backend/domain/v1/data_integration/models/bases/sr_report_images.py`
- 파싱 상태 DTO: `backend/domain/v1/data_integration/models/states/sr_parsing_state.py` (`SrReportImagesRow`)

---

## 11. Quick Start

- 환경변수: **`SR_IMAGE_OUTPUT_DIR`** (필수 권장), (선택) `SR_IMAGE_SKIP_INDEX_PAGES=1`, `SR_IMAGE_MAX_EDGE=2048`, `SR_IMAGE_DEBUG=1`
- **에이전트 직행 (PDF는 DB 경로 또는 base64)**:

```bash
curl -X POST http://localhost:8000/data-integration/sr-agent/extract-and-save/images-agentic \
  -H "Content-Type: application/json" \
  -d "{\"report_id\": \"<uuid>\", \"pdf_bytes_b64\": null, \"image_output_dir\": null}"
```

`image_output_dir`가 null이면 환경변수 `SR_IMAGE_OUTPUT_DIR` 사용. `pdf_bytes_b64`는 agentic 경로에서 필수(DB에 PDF 경로 없음).

- **LangGraph + SRAgent fetch**: `POST .../extract-and-save/images` — body에 `image_output_dir`로 저장 경로 전달 가능.

- 응답: `saved_count`, `db_sr_report_images_row_count`, `images_agent_*`, `errors`

---

**문서 버전**: 초안 (코드베이스 스냅샷 기준)  
**다음 액션**: Phase 1 체크리스트부터 구현 착수 시, 이 문서의 §6 멱등성 전략을 팀에서 한 가지로 확정할 것.
