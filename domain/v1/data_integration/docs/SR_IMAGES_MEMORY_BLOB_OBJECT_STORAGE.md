# SR 이미지: 디스크 경로 → 메모리 / DB Blob / 객체 스토리지 전환 구현 가이드

> **구현 상태 (코드)**  
> - `extract_report_images_to_memory` · `SR_IMAGE_STORAGE` (`disk` \| `memory` \| `s3`) · `spokes/infra/sr_image_object_storage.py` 반영됨.  
> - DB `BYTEA`(blob) 컬럼은 **미구현** — 필요 시 §5 + Alembic 추가.

> **목적**: `extract_report_images`가 `output_dir`에 파일을 쓰고, `SRImagesAgent`가 `SR_IMAGE_OUTPUT_DIR`를 요구하는 현재 구조를, **디스크 없이(또는 DB/S3에만)** 끝낼 수 있게 바꾸기 위한 **구체적 작업 목록**입니다.  
> **전제**: `image_file_path` 컬럼은 이미 제거됨. 픽셀 데이터는 **새 컬럼·JSONB·외부 URL** 중 하나로 “어디에 저장할지”를 정해야 함.

---

## 1. 현재 구조 (변경 전 기준)

| 단계 | 파일 | 동작 |
|------|------|------|
| 추출 | `backend/domain/shared/tool/parsing/image_extractor.py` | `extract_report_images(...)` → `output_dir/report_id/` 아래에 `{page}_{idx}.{ext}` **파일 쓰기** → `images_by_page`에 `"path"` 포함 |
| 매핑 | `backend/domain/shared/tool/sr_report/images/sr_image_mapping.py` | `path`는 메타에 안 넣고 `size_bytes`, `width` 등만 행으로 |
| 에이전트 | `backend/domain/v1/data_integration/spokes/agents/sr_images_agent.py` | `image_output_dir` 또는 `SR_IMAGE_OUTPUT_DIR` **없으면 즉시 실패** |
| DB | `backend/domain/v1/data_integration/models/bases/sr_report_images.py` | `image_file_path` 없음, 메타만 |

**핵심**: 픽셀은 **디스크에만** 있고 DB에는 없음. 디스크를 없애면 픽셀을 **다른 곳**에 두어야 함.

---

## 2. 선택지 3가지 (구현 난이도·운영 특성)

| 방식 | DB | 장점 | 단점 | 권장 상황 |
|------|-----|------|------|-----------|
| **A. 메모리만 + 메타만 DB** | 기존 스키마 유지 | 구현 단순, DB 용량 작음 | 요청 끝나면 픽셀 소실, **다시 조회/캡션 불가** | 배치 파이프라인에서 “당장 통계만” |
| **B. PostgreSQL Blob** | `BYTEA` 또는 `extracted_data`에 base64 | 단일 DB로 일원화 | DB 팽창, 백업·복제 부담, **대용량 PDF 비권장** | 소규모·내부망 |
| **C. 객체 스토리지 (S3/MinIO 등)** | 키/URL만 (컬럼 또는 JSONB) | 확장성·CDN | 인프라·권한·비용 | **운영·멀티 인스턴스** |

아래는 **실제 코드로 바로 착수할 수 있게** 단계별로 나눔.

---

## 3. 공통 1단계: 추출 함수를 “디스크 없이” 분기

### 3.1 새 함수 시그니처 (권장)

**파일**: `image_extractor.py` (동일 파일에 추가)

```python
def extract_report_images_to_memory(
    pdf_bytes: bytes,
    pages: List[int],
    report_id: str,
    *,
    index_page_numbers: Optional[List[int]] = None,
    skip_index_pages: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    extract_report_images 와 동일 필터/휴리스틱이지만,
    디스크에 쓰지 않고 각 이미지에 대해 raw bytes 를 포함해 반환.

    Returns:
        {
            "success": bool,
            "images_by_page": {
                page: [
                    {
                        "image_bytes": bytes,      # 필수 (또는 memoryview)
                        "mime_type": str,          # 예: "image/png"
                        "width": int | None,
                        "height": int | None,
                        "size_bytes": int,
                        "image_index": int,
                        # "path" 없음
                    },
                    ...
                ]
            },
            "error": str | None,
            "skipped_pages": [int],
        }
    """
```

### 3.2 구현 방법 (복사·수정)

- 기존 `extract_report_images`의 **루프 본문**(약 `doc.extract_image` ~ `page_entries.append`)을 복사한다.
- **`sub.mkdir` / `fpath.write_bytes` / `fpath.stat`** 삭제.
- `size_bytes`는 `len(raw)` 로 계산.
- `mime_type`은 `ext`에 매핑 (`png` → `image/png`, `jpeg`/`jpg` → `image/jpeg`, …).
- `page_entries.append`에 `"image_bytes": raw`, `"mime_type": ...` 넣기.

### 3.3 `map_extracted_images_to_sr_report_rows` 확장

**파일**: `sr_image_mapping.py`

- 옵션 1: `images_by_page` 항목에 `image_bytes`가 있으면 **저장하지 않고** `extracted_data`에 넣지 않음(Blob 단계에서 별도 처리).
- 옵션 2: `map_extracted_images_to_sr_report_rows`에 인자 `include_blob_in_extracted_data: bool = False` 추가  
  - `True`일 때만 `extracted_data["image_b64"] = base64.b64encode(...).decode("ascii")` (**DB 크기 폭주** 주의).

---

## 4. 방식 A — 메모리만 + 메타 DB (이미지 재조회 불필요)

### 목표

- `SRImageOutputDir` **필수 조건 제거**.
- `extract_report_images_to_memory` → `map...` → `save_sr_report_images_batch` (메타만).

### 작업 목록

1. `SRImagesAgent.execute`에서 `_resolve_image_output_dir` 실패 시 **에러 대신** `extract_report_images_to_memory` 호출 분기 (환경변수 `SR_IMAGE_STORAGE=memory` 권장).
2. `_extract()` 내부를 `extract_report_images_to_memory`로 교체.
3. 단위 테스트: 디스크 없이 `saved_count > 0` (메타만).

### 제한

- 나중에 “저장된 이미지 보여주기” API가 필요하면 **방식 B/C**로 가야 함.

---

## 5. 방식 B — PostgreSQL에 바이너리 저장

### 5.1 스키마

**옵션 B1** (추천): `BYTEA` 컬럼

```sql
ALTER TABLE sr_report_images ADD COLUMN image_blob BYTEA NULL;
```

- Alembic: `backend/alembic/versions/017_sr_images_blob.py` (`revision`: `017_sr_images_blob`).
- `revision` id는 **32자 이하** (PostgreSQL `alembic_version` 길이 제한).

**옵션 B2**: `extracted_data` JSONB에 base64

```json
{ "image_b64": "<base64>", "mime_type": "image/png" }
```

- 스키마 변경 없음. **대신 행당 JSON 크기**가 커짐.

### 5.2 저장 코드

**파일**: `sr_save_tools.py` → `save_sr_report_images_batch`, 단건 `save_sr_report_image`(선택 `image_blob_base64`)

- ORM `SrReportImage.image_blob` (B1).
- 배치: 행 dict에 `image_blob`(bytes) 직접 전달 가능.
- 매핑: `sr_image_mapping.map_extracted_images_to_sr_report_rows` — 환경변수 **`SR_IMAGE_PERSIST_BLOB=1`** 일 때만 `image_bytes`/`image_blob` → `image_blob` (상한 **`SR_IMAGE_MAX_BLOB_BYTES`**, 기본 5MB).

### 5.3 읽기 API (선택)

- `GET /api/.../sr-report-images/{id}/raw` → `Response(content=row.image_blob, media_type=mime)`  
- 또는 presigned URL 없이 **직접 스트리밍** (내부망).

### 5.4 운영 제한

- 이미지 한 장 수 MB × 페이지 수 → **DB 용량·WAL** 모니터링.
- 권장: **최대 바이트** 환경변수 `SR_IMAGE_MAX_BLOB_BYTES` 초과 시 스킵 또는 리사이즈.

---

## 6. 방식 C — S3 / MinIO (권장: 운영)

### 6.1 환경 변수

```env
SR_IMAGE_STORAGE=s3
AWS_S3_BUCKET=your-bucket
AWS_S3_PREFIX=sr-images/
AWS_REGION=ap-northeast-2
# 또는 MinIO
S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### 6.2 객체 키 규칙 (예시)

```
{prefix}{report_id}/{page_number}_{image_index}.{ext}
```

### 6.3 DB에 저장할 값

**옵션 C1**: `extracted_data`에만 저장

```json
{
  "storage": "s3",
  "bucket": "your-bucket",
  "key": "sr-images/uuid/131_0.png",
  "etag": "..."
}
```

**옵션 C2**: 전용 컬럼 `image_object_key TEXT` (nullable) — Alembic 추가.

### 6.4 업로드 모듈 (신규 파일 권장)

`backend/domain/v1/data_integration/spokes/infra/sr_image_object_storage.py`

```python
def upload_sr_image_bytes(
    *,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str,
) -> dict:
    """boto3 client.put_object(...). 반환: {etag, version_id?}"""
```

- 의존성: `boto3` (requirements에 추가).

### 6.5 파이프라인 순서

1. `extract_report_images_to_memory` → 각 항목에 대해 `upload_sr_image_bytes`.
2. 업로드 성공 시 DB 행의 `extracted_data` 또는 `image_object_key` 갱신.
3. **로컬 디스크 쓰기 없음**.

### 6.6 조회

- 프론트: 백엔드가 **presigned GET URL** 발급 API 제공, 또는 프록시 스트리밍.

---

## 7. `SRImagesAgent` 변경 체크리스트

**파일**: `sr_images_agent.py`

1. [x] `SR_IMAGE_STORAGE` 환경변수: `disk` | `memory` | `s3` (미설정 시 **`memory`** — 출력 디렉터리 없이 메타만 DB).
2. [ ] `disk`: 기존 `extract_report_images` + `output_dir` 필수 유지.
3. [ ] `memory`: `extract_report_images_to_memory` + 메타만 저장.
4. [ ] `s3`: `memory` 추출 후 업로드 + DB에 키/메타.
5. [ ] `disk`가 아닐 때 `image_output_dir` 없어도 에러 내지 않기 (또는 S3 모드일 때만 완화).

---

## 8. API / 워크플로

- **LangGraph `extract-and-save/images`**: `image_output_dir` / `SR_IMAGE_OUTPUT_DIR` — `SR_IMAGE_STORAGE=s3`이면 **선택**으로 문서화.
- **`images-agentic`**: `pdf_bytes_b64` 필수 유지. 이미지 저장 모드는 서버 환경변수로 통일.

---

## 9. 테스트

| 테스트 | 내용 |
|--------|------|
| 단위 | `extract_report_images_to_memory` → `images_by_page[1][0]["image_bytes"]` len > 0 |
| 단위 | `save_sr_report_images_batch`에 `image_blob` 전달 시 SELECT로 BYTEA 복원 |
| 통합 | S3 모드 mock (`moto` 또는 localstack)로 put_object 호출 검증 |
| 부하 | 대용량 PDF에서 메모리 피크 측정 (스트리밍 업로드 고려) |

---

## 10. 구현 순서 권장

1. **`extract_report_images_to_memory` 추가** + 기존 디스크 경로와 **동일 결과 개수** 비교 테스트 (샘플 PDF 1장).
2. **`SR_IMAGE_STORAGE=memory`** 로 SRImagesAgent 분기 + 메타만 저장.
3. (필요 시) **Alembic `image_blob`** + 저장/조회 API.
4. (운영) **S3 업로드 모듈** + `SR_IMAGE_STORAGE=s3` + `extracted_data` 또는 `image_object_key`.

---

## 11. 관련 문서

- [SR_IMAGES_PARSING_DESIGN.md](./SR_IMAGES_PARSING_DESIGN.md)
- [PDF_PARSING_IN_MEMORY.md](./PDF_PARSING_IN_MEMORY.md)

---

## 12. 리비전 ID (Alembic)

새 마이그레이션 추가 시 **`alembic_version.version_num`은 VARCHAR(32)** 이므로, `revision = "017_sr_images_blob"` 처럼 **항상 32자 이하**로 둘 것.
