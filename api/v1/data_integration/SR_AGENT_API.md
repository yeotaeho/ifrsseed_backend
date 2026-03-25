# SR Agent API - 단계별 추출 및 저장

SR 보고서를 검색, 다운로드, 파싱, 저장하는 단계별 API 엔드포인트입니다.

## 개요

기존의 통합 엔드포인트(`/extract?save_to_db=true`)는 메타데이터, 인덱스, 본문, 이미지를 한 번에 처리하려고 시도했으나, LLM 토큰 제한으로 인해 본문 저장 단계에서 실패했습니다.

**해결 방안**: 각 단계를 독립적인 엔드포인트로 분리하여, 각자 독립적인 메시지 히스토리를 유지하고 토큰 제한 문제를 해결합니다.

## 새로운 엔드포인트 구조

### 1단계: 메타데이터 추출 및 저장

```http
POST /data-integration/sr-agent/extract-and-save/metadata
```

**요청 본문**:
```json
{
  "company": "samsungsds",
  "year": 2024,
  "company_id": "optional-uuid"
}
```

**응답**:
```json
{
  "success": true,
  "message": "메타데이터 저장 완료",
  "report_id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06",
  "historical_sr_reports": {
    "id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06",
    "company_id": null,
    "report_year": 2024,
    "report_name": "삼성SDS 지속가능경영보고서 2024",
    "source": "sr_agent",
    "total_pages": 144,
    "index_page_numbers": [138, 139, 140, 141, 142, 143]
  }
}
```

**역할**:
- SR 보고서 PDF를 검색하여 다운로드
- 메타데이터(총 페이지 수, 인덱스 페이지 번호 등) 파싱
- `historical_sr_reports` 테이블에 저장
- **중요**: 반환된 `report_id`를 다음 단계에서 사용

---

### 2단계: 인덱스 추출 및 저장

```http
POST /data-integration/sr-agent/extract-and-save/index
```

**요청 본문**:
```json
{
  "company": "samsungsds",
  "year": 2024,
  "report_id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06"
}
```

**응답**:
```json
{
  "success": true,
  "message": "인덱스 141건 저장 완료",
  "saved_count": 141,
  "errors": []
}
```

**역할**:
- 메타데이터에서 `index_page_numbers` 조회
- SR 보고서 인덱스 페이지 파싱 (GRI, IFRS, SASB 지표)
- `sr_report_index` 테이블에 배치 저장
- 부분 실패 시 `errors` 배열에 오류 정보 포함

---

### 3단계: 본문 추출 및 저장

```http
POST /data-integration/sr-agent/extract-and-save/body
```

**요청 본문**:
```json
{
  "company": "samsungsds",
  "year": 2024,
  "report_id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06"
}
```

**응답**:
```json
{
  "success": true,
  "message": "본문 144건 저장 완료",
  "saved_count": 144,
  "errors": []
}
```

**역할**:
- SR 보고서 전체 페이지의 본문 텍스트 추출
- `sr_report_body` 테이블에 페이지별로 저장
- 문단 정보(`paragraphs`) 포함

---

### 4단계: 이미지 추출 및 저장 (선택)

```http
POST /data-integration/sr-agent/extract-and-save/images
```

**요청 본문**:
```json
{
  "company": "samsungsds",
  "year": 2024,
  "report_id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06",
  "image_output_dir": "/path/to/save/images"
}
```

**응답**:
```json
{
  "success": true,
  "message": "이미지 50건 저장 완료",
  "saved_count": 50,
  "errors": []
}
```

**역할**:
- SR 보고서에서 이미지 추출
- `sr_report_images` 테이블에 메타데이터 저장
- 기본(`SR_IMAGE_STORAGE=memory`, 미설정 시 동일)은 로컬 파일 없이 메타만 저장. `SR_IMAGE_STORAGE=disk`일 때만 `image_output_dir` 또는 `SR_IMAGE_OUTPUT_DIR`에 파일 저장
- 저장 성공 후 `OPENAI_API_KEY`가 있으면 **자동 VLM 보강**(캡션·타입 등). 끄려면 `SR_IMAGE_VLM_AUTO_AFTER_SAVE=0`. 응답 필드 `images_vlm_auto_*`

#### 이미지 에이전트 직행 (LangGraph·재검색 없음)

```http
POST /data-integration/sr-agent/extract-and-save/images-agentic
```

**요청 본문**:
```json
{
  "report_id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06",
  "pdf_bytes_b64": null,
  "image_output_dir": null
}
```

- `pdf_bytes_b64` 없음 → **400** (DB에 PDF 로컬 경로는 저장하지 않음). 본문/이미지 agentic API는 **base64 PDF를 반드시** 보내야 합니다.
- `SR_IMAGE_STORAGE=disk`일 때만 `image_output_dir` 또는 `SR_IMAGE_OUTPUT_DIR` 필요. 기본 memory는 불필요.

**응답** (추가 필드): `db_sr_report_images_row_count`, `images_agent_success`, `images_agent_message`, `images_vlm_auto_*`(자동 보강) 등.

#### 이미지 VLM 메타 보강 (2단계, OpenAI)

저장된 `sr_report_images` 행에 대해 `image_type` / `caption_text` / `caption_confidence` 를 채웁니다. 바이트는 `image_blob` 또는 S3(`extracted_data`)에서 읽습니다.

```http
POST /data-integration/sr-agent/enrich-images-vlm
```

**환경**: `OPENAI_API_KEY`. VLM 모델명은 코드에서 `gpt-5-mini` 고정.

**요청 본문**:
```json
{
  "report_id": "1f0c9999-f5dd-46ca-86db-f34c24e6ab06",
  "skip_if_caption_set": false
}
```

---

## 전체 워크플로우 예시

### Python 예시

```python
import httpx

BASE_URL = "http://localhost:9002/data-integration/sr-agent"

async def extract_and_save_sr_report(company: str, year: int):
    async with httpx.AsyncClient() as client:
        # 1. 메타데이터 저장
        meta_response = await client.post(
            f"{BASE_URL}/extract-and-save/metadata",
            json={"company": company, "year": year}
        )
        meta_data = meta_response.json()
        
        if not meta_data["success"]:
            print(f"메타데이터 저장 실패: {meta_data['message']}")
            return
        
        report_id = meta_data["report_id"]
        print(f"✓ 메타데이터 저장 완료: {report_id}")
        
        # 2. 인덱스 저장
        index_response = await client.post(
            f"{BASE_URL}/extract-and-save/index",
            json={"company": company, "year": year, "report_id": report_id}
        )
        index_data = index_response.json()
        print(f"✓ 인덱스 {index_data['saved_count']}건 저장 완료")
        
        # 3. 본문 저장
        body_response = await client.post(
            f"{BASE_URL}/extract-and-save/body",
            json={"company": company, "year": year, "report_id": report_id}
        )
        body_data = body_response.json()
        print(f"✓ 본문 {body_data['saved_count']}건 저장 완료")
        
        # 4. 이미지 저장 (선택)
        images_response = await client.post(
            f"{BASE_URL}/extract-and-save/images",
            json={"company": company, "year": year, "report_id": report_id}
        )
        images_data = images_response.json()
        print(f"✓ 이미지 {images_data['saved_count']}건 저장 완료")
        
        print(f"\n전체 저장 완료! report_id: {report_id}")

# 실행
import asyncio
asyncio.run(extract_and_save_sr_report("samsungsds", 2024))
```

### cURL 예시

```bash
# 1. 메타데이터 저장
METADATA_RESPONSE=$(curl -s -X POST "http://localhost:9002/data-integration/sr-agent/extract-and-save/metadata" \
  -H "Content-Type: application/json" \
  -d '{"company":"samsungsds","year":2024}')

REPORT_ID=$(echo $METADATA_RESPONSE | jq -r '.report_id')
echo "메타데이터 저장 완료: $REPORT_ID"

# 2. 인덱스 저장
curl -X POST "http://localhost:9002/data-integration/sr-agent/extract-and-save/index" \
  -H "Content-Type: application/json" \
  -d "{\"company\":\"samsungsds\",\"year\":2024,\"report_id\":\"$REPORT_ID\"}"

# 3. 본문 저장
curl -X POST "http://localhost:9002/data-integration/sr-agent/extract-and-save/body" \
  -H "Content-Type: application/json" \
  -d "{\"company\":\"samsungsds\",\"year\":2024,\"report_id\":\"$REPORT_ID\"}"

# 4. 이미지 저장
curl -X POST "http://localhost:9002/data-integration/sr-agent/extract-and-save/images" \
  -H "Content-Type: application/json" \
  -d "{\"company\":\"samsungsds\",\"year\":2024,\"report_id\":\"$REPORT_ID\"}"
```

---

## 장점

### 1. 토큰 제한 문제 해결
각 엔드포인트가 독립적인 메시지 히스토리를 유지하므로, 인덱스 141건 데이터가 본문 파싱에 영향을 주지 않습니다.

### 2. 실패 복구 용이
인덱스 저장 성공 후 본문 저장만 재시도 가능. 전체를 다시 실행할 필요가 없습니다.

### 3. 선택적 실행
메타데이터와 인덱스만 필요한 경우, 본문과 이미지 저장을 생략할 수 있습니다.

### 4. 진행 상황 추적
각 단계의 성공 여부와 저장 건수를 확인할 수 있습니다.

### 5. 부분 실패 처리
배치 저장 중 일부가 실패해도 나머지는 저장되며, `errors` 배열로 실패 정보를 확인할 수 있습니다.

---

## 기존 엔드포인트 비교

### 기존: `/extract?save_to_db=true` (문제)

```
[Metadata] → [Index] → [Body] → ❌ 토큰 초과 (275K > 272K)
```

- 모든 단계를 하나의 LLM 세션에서 처리
- 인덱스 141건 데이터가 메시지 히스토리에 누적
- 본문 파싱 결과 추가 시 토큰 한계 초과

### 새로운: 단계별 엔드포인트 (해결)

```
[Metadata] ✓ → [Index] ✓ → [Body] ✓ → [Images] ✓
  (독립)       (독립)       (독립)      (독립)
```

- 각 단계가 독립적인 HTTP 요청
- 각자 깨끗한 메시지 히스토리로 시작
- 토큰 제한 문제 없음

---

## 에러 처리

각 엔드포인트는 다음과 같은 에러 응답을 반환할 수 있습니다:

```json
{
  "success": false,
  "message": "PDF 다운로드 실패",
  "saved_count": 0,
  "errors": []
}
```

배치 저장 중 부분 실패:

```json
{
  "success": true,
  "message": "본문 142건 저장 완료",
  "saved_count": 142,
  "errors": [
    {
      "index": 50,
      "page": 51,
      "error": "content_text is too long"
    },
    {
      "index": 100,
      "page": 101,
      "error": "duplicate key"
    }
  ]
}
```

---

## 데이터베이스 스키마

### 1. `historical_sr_reports`
- `id` (UUID, PK)
- `company_id` (UUID, FK to companies)
- `report_year` (int)
- `report_name` (text)
- `source` (text)
- `total_pages` (int)
- `index_page_numbers` (int[])
- `created_at` (timestamp)

### 2. `sr_report_index`
- `id` (UUID, PK)
- `report_id` (UUID, FK to historical_sr_reports)
- `index_type` (text: "gri" | "ifrs" | "sasb")
- `index_page_number` (int, nullable)
- `dp_id` (text, indexed)
- `dp_name` (text, nullable)
- `page_numbers` (int[])
- `section_title` (text, nullable)
- `remarks` (text, nullable)
- `parsed_at` (timestamp)
- `parsing_method` (text, default: "docling")
- `confidence_score` (numeric(5,2), nullable)

### 3. `sr_report_body`
- `id` (UUID, PK)
- `report_id` (UUID, FK to historical_sr_reports)
- `page_number` (int)
- `is_index_page` (boolean)
- `content_text` (text)
- `content_type` (text, nullable)
- `paragraphs` (jsonb)
- `embedding_id` (UUID, nullable)
- `embedding_status` (text, default: "pending")

### 4. `sr_report_images`
- `id` (UUID, PK)
- `report_id` (UUID, FK to historical_sr_reports)
- `page_number` (int)
- `image_index` (int, nullable)
- `image_width` (int, nullable)
- `image_height` (int, nullable)
- `image_type` (text, nullable)
- `caption_text` (text, nullable)
- `caption_confidence` (numeric(5,2), nullable)
- `extracted_data` (jsonb, nullable)
- `caption_embedding_id` (UUID, nullable)
- `embedding_status` (text, default: "pending")

---

## 참고

- **파싱 도구**: Docling (primary) + LlamaParse (fallback)
- **LLM**: OpenAI GPT-5-mini (메타데이터 저장에만 사용, 인덱스/본문/이미지는 직접 파싱)
- **배치 저장**: 인덱스, 본문, 이미지는 모두 배치로 저장하여 성능 최적화
- **멱등성**: 같은 `report_id`로 재호출 시 중복 저장될 수 있으므로 주의

---

## 마이그레이션 가이드

### 기존 코드에서 마이그레이션

**Before**:
```python
response = await client.get(
    "http://localhost:9002/data-integration/sr-agent/extract",
    params={"company": "samsungsds", "year": 2024, "save_to_db": True}
)
```

**After**:
```python
# 1. 메타데이터
meta = await client.post(
    "http://localhost:9002/data-integration/sr-agent/extract-and-save/metadata",
    json={"company": "samsungsds", "year": 2024}
)
report_id = meta.json()["report_id"]

# 2. 인덱스
await client.post(
    "http://localhost:9002/data-integration/sr-agent/extract-and-save/index",
    json={"company": "samsungsds", "year": 2024, "report_id": report_id}
)

# 3. 본문
await client.post(
    "http://localhost:9002/data-integration/sr-agent/extract-and-save/body",
    json={"company": "samsungsds", "year": 2024, "report_id": report_id}
)

# 4. 이미지 (선택)
await client.post(
    "http://localhost:9002/data-integration/sr-agent/extract-and-save/images",
    json={"company": "samsungsds", "year": 2024, "report_id": report_id}
)
```

---

## 문의

- 구현: `backend/api/v1/data_integration/sr_agent_router.py`
- 파싱 도구: `backend/domain/shared/tool/sr_report_tools_docling.py`
- 저장 도구: `backend/domain/shared/tool/sr_save_tools.py`
