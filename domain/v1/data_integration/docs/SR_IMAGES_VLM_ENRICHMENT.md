# SR 이미지 VLM 메타 보강 (`image_type` · `caption_text` · `caption_confidence`)

## 문서 개요

**목적**: 현재 **PyMuPDF 기반 결정적 파이프라인**(`SRImagesAgent`)이 채우는 필드(페이지·크기·`extracted_data.mime_type` 등)에 더해, **비전 LLM(VLM)**으로 `sr_report_images`의 **`image_type`**, **`caption_text`**, **`caption_confidence`** 를 채우기 위한 **설계**와 **구현 단계**를 구분해 정리합니다.

**관련 문서**

| 문서 | 내용 |
|------|------|
| [SR_IMAGES_PARSING_DESIGN.md](./SR_IMAGES_PARSING_DESIGN.md) | 이미지 추출·매핑·저장 전체 플로우 |
| [SR_IMAGES_MEMORY_BLOB_OBJECT_STORAGE.md](./SR_IMAGES_MEMORY_BLOB_OBJECT_STORAGE.md) | memory / BYTEA / S3 저장 모드 |
| [DATABASE_TABLES_STRUCTURE.md](../../ifrs_agent/docs/DATABASE_TABLES_STRUCTURE.md) | `sr_report_images` 스키마 |

**현재 코드 기준 요약**

- **추출**: `backend/domain/shared/tool/parsing/image_extractor.py` — `extract_report_images` / `extract_report_images_to_memory` (LLM 없음).
- **매핑**: `backend/domain/shared/tool/sr_report/images/sr_image_mapping.py` — `map_extracted_images_to_sr_report_rows` (`image_type`·캡션은 추출 항목에 없으면 `NULL`).
- **에이전트**: `backend/domain/v1/data_integration/spokes/agents/sr_images_agent.py` — 추출 → 매핑 → `save_sr_report_images_batch`.
- **워크플로**: `hub/orchestrator/sr_workflow.py` — `_save_images_node` → `AgentRouter` → `sr_images_agent`.

---

## Part A — 설계 (Design)

### A.1 목표 컬럼과 역할

| 컬럼 | 의도 | 비고 |
|------|------|------|
| `image_type` | 차트·사진·표 등 **의미적 분류** | 앱·검색에서 필터. 고정 enum 권장. |
| `caption_text` | 이미지에 대한 **짧은 자연어 설명** (한국어 등) | RAG·FactSheet용. |
| `caption_confidence` | 위 분류/캡션에 대한 **신뢰도** | 모델이 수치를 주지 않으면 NULL 또는 규칙 기반 대용. |

PyMuPDF만으로는 위 세 가지를 **의미 있게** 채우기 어렵고, **이미지 입력을 받는 LLM(VLM) API 호출**이 전제에 가깝습니다.

### A.2 입력 소스 (이미지 바이트 확보)

현재 저장 모드에 따라 VLM에 넘길 픽셀 출처가 달라집니다.

| `SR_IMAGE_STORAGE` | VLM 입력 확보 |
|---------------------|----------------|
| `memory` | `extract_report_images_to_memory`가 준 `image_bytes` (또는 `SR_IMAGE_PERSIST_BLOB=1` 시 DB `image_blob`과 동일 원천). |
| `disk` | 디스크에 쓴 파일을 읽거나, 추출 루프에서 **메모리 바이트를 VLM 단계까지 전달** (이중 I/O 방지 설계 권장). |
| `s3` | `extracted_data`의 키로 **다운로드** 후 base64, 또는 **presigned URL**을 VLM API가 지원하면 URL 전달. |

**설계 결정**: VLM 단계는 가능하면 **`(report_id, page_number, image_index)` 또는 `sr_report_images.id`와 1:1 매핑**이 되게 하여, DB 업데이트 시 조건을 단순화합니다.

### A.3 아키텍처 옵션

| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **① 인라인** | `SRImagesAgent.execute` 안에서 추출 직후·저장 직전에 이미지마다 VLM 호출 후 `rows`에 병합 | 한 번의 호출로 완결 | PDF당 이미지 수만큼 동기 API → **지연·비용** 폭증, 실패 시 전체 정책 복잡 |
| **② 2단계 INSERT 후 UPDATE** | 기존과 동일하게 **메타만 먼저** `save_sr_report_images_batch`, 이후 **배치/비동기**로 `id`별 VLM → `UPDATE` | 기존 파이프라인 유지, **재시도·스킵** 용이 | 스키마·트랜잭션 2회, 중간에 `caption` NULL 구간 존재 |
| **③ 비동기 워커** | 큐(예: `embedding_status` 연계)에 `report_id` 또는 `image_id` 적재 후 워커가 VLM | API 서버 부하 분리 | 인프라 추가 |

**권장 (현재 구조와의 정렬)**:

- **1차**: **② 2단계** — 결정적 추출·저장은 그대로 두고, **별도 모듈** `enrich_sr_report_images_with_vlm(...)` (이름 예시)로 **행 `id` 기준 UPDATE** 또는 **replace_existing=false인 patch 저장** 정책을 택함.
- **고부하 시**: 동일 로직을 워커 **③**으로 옮기기만 하면 됨 (입출력 계약 동일).

### A.4 LLM 계약 (API·출력 형식)

- **모델**: 구현에서는 OpenAI **`gpt-5-mini`** 를 코드 상수로 고정 (`DEFAULT_VLM_MODEL`).
- **입력**: 이미지 `base64` + `image/jpeg` 등 **media type** (`extracted_data.mime_type` 활용).
- **출력**: **JSON만** 반환하도록 시스템/개발자 프롬프트 고정 (파싱 실패 방지).

**응답 스키마 예 (의사 코드)**

```json
{
  "image_type": "chart | graph | photo | diagram | table | logo | unknown",
  "caption": "한국어 1~3문장",
  "confidence": 0.85
}
```

- `image_type`: 서버에서 **허용 enum**으로 검증·잘못된 값은 `unknown`.
- `confidence`: 모델이 숫자를 제공하지 않으면 **NULL 저장** 또는 규칙 `0.5` 등은 **제품 정책**으로 명시.

### A.5 `embedding_status` · `caption_embedding_id`와의 관계

- VLM으로 **캡션이 채워진 뒤**에만 캡션 임베딩을 넣는 경우: 별도 배치가 `caption_embedding_id`를 갱신하고 `embedding_status`를 `complete` 등으로 바꿈.
- 본 문서 범위는 **VLM 메타 보강**까지이며, **벡터 인덱싱**은 기존 `caption_embedding_id`·`embedding_status` 정책과 맞춰 후속 단계로 둡니다.

### A.6 비용·안정성

- **배치 크기**: 이미지 N개/분 동시성 상한 (`asyncio.Semaphore` 또는 워커 concurrency).
- **재시도**: 429/5xx만 지수 백오프; **동일 이미지 재호출**은 멱등하게 `UPDATE`만 수행.
- **티어**: 기본 **mini** → 실패·`unknown` 비율 높을 때만 **4o** 재시도(선택).

---

## Part B — 구현 (Implementation)

구현은 **의존성이 적은 순**으로 쌓습니다. 단계를 나누어 PR을 쪼개기 좋게 정리했습니다.

### B.1 Phase 1 — 환경·설정

- `OPENAI_API_KEY` (필수). VLM 모델·켜짐 여부는 코드 상수(`DEFAULT_VLM_MODEL=gpt-5-mini`, 엔드포인트 호출 시 보강).
- (선택) 동시성·재시도는 향후 `SR_IMAGE_VLM_CONCURRENCY` 등으로 확장 가능.

### B.2 Phase 2 — 순수 클라이언트 모듈

- 구현: `backend/domain/v1/data_integration/spokes/infra/sr_image_vlm_client.py` (`vlm_describe_image`, `DEFAULT_VLM_MODEL` = `gpt-5-mini`).
- 책임: **bytes + mime → JSON 스키마 dict** 반환. DB·`report_id` 무관.
- 단위 테스트: **API 모킹**으로 JSON 파싱·enum 클램프 검증.

### B.3 Phase 3 — 보강 서비스 (도메인)

- 구현: `backend/domain/v1/data_integration/spokes/infra/sr_image_vlm_enrichment.py` (`enrich_sr_report_images_vlm`, `image_blob` 또는 S3 `extracted_data`에서 바이트 로드).
- 출력: `id` → `{image_type, caption_text, caption_confidence}`.
- `caption_confidence`를 모델이 안 주면 **NULL** 처리 명시.

### B.4 Phase 4 — 저장소 연동

- **옵션 A**: SQLAlchemy로 `SrReportImage` **id 단위 UPDATE** (권장).
- **옵션 B**: 기존 `save_sr_report_images_batch` 확장은 **이미 replace/delete 패턴**과 섞이면 복잡해지므로, **첫 저장은 기존 유지 + 보강만 UPDATE**가 안전.

### B.5 Phase 5 — `SRImagesAgent` / 워크플로 연결

| 통합 방식 | 작업 |
|-----------|------|
| **동일 요청 내 (구현됨)** | `save_images` 노드에서 배치 저장 성공 후 `maybe_auto_enrich_after_image_save(report_id)` 호출. `POST /extract-and-save/images`, `POST /extract-and-save/images-agentic` 응답에 `images_vlm_auto_*` 필드. |
| **끄기** | `SR_IMAGE_VLM_AUTO_AFTER_SAVE=0` 또는 `OPENAI_API_KEY` 미설정 시 자동 보강 스킵. |
| **수동** | `POST /enrich-images-vlm` 으로 동일 보강만 재실행 가능. |

### B.6 Phase 6 — API·운영

- 구현: `POST /data-integration/sr-agent/enrich-images-vlm` (본문: `{ "report_id": "<uuid>", "skip_if_caption_set": false }`).
- 로그: 보강 성공/실패 건수, 모델명, 토큰 사용량(가능 시).

### B.7 Phase 7 — 테스트

- 통합 테스트: DB에 시드 행 + VLM 모킹 → 컬럼 갱신 검증.
- 회귀: 보강 엔드포인트를 호출하지 않으면 **기존 추출·저장만**과 동일.

### B.8 완료 기준 (체크리스트)

- [ ] VLM 끔: 기존과 동일하게 동작.
- [ ] VLM 켬: `image_type` / `caption_text` / `caption_confidence` 중 최소 전자 둘 이상이 신뢰 가능하게 채워짐.
- [ ] 실패 시에도 추출·저장 파이프라인은 깨지지 않음(보강만 실패 로그).

---

## 요약

- **설계**: VLM은 **PyMuPDF 추출과 분리**하는 **2단계(저장 후 보강)** 를 권장하고, 계약은 **JSON + enum 검증**으로 고정합니다.
- **구현**: **클라이언트 → 도메인 보강 → UPDATE → (선택) 워크플로/API** 순으로 올리면 현재 `SRImagesAgent`·`sr_workflow` 구조를 크게 흔들지 않습니다.

이 문서는 구현 시 PR 설명·태스크 분해의 기준으로 사용하고, 세부 모델명·가격은 OpenAI(또는 선택 공급자) **공식 문서**를 따릅니다.
