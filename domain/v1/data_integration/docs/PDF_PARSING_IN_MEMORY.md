# PDF 파싱: 저장 없이 다운로드 후 메모리에서 파싱

개발 단계에서는 PDF를 `data_integration/data/`에 저장한 뒤 경로로 파싱하지만,
**운영/개발 완료 후**에는 PDF를 **디스크에 저장하지 않고** 다운로드한 바이트만 메모리에 두고 파싱한 뒤, 결과만 DB 테이블에 저장하는 방식으로 전환할 수 있습니다.

---

## 1. 가능 여부

**가능합니다.** PyMuPDF(`fitz`)는 파일 경로뿐 아니라 **bytes/bytearray**로도 PDF를 열 수 있습니다.

- **파일 경로**: `fitz.open(pdf_path)` — 기존 방식
- **메모리**: `fitz.open(stream=pdf_bytes, filetype="pdf")` — 디스크 저장 없이 파싱

따라서 **다운로드 → bytes 유지 → 메모리에서 파싱 → DB 저장** 흐름으로 PDF 파일을 저장하지 않아도 됩니다.

---

## 2. 현재 vs 목표 흐름

| 구분 | 현재 (개발용) | 목표 (저장 없이) |
|------|----------------|-------------------|
| 다운로드 | MCP `download_pdf`가 `data/`에 파일 저장 후 `path` 반환 | URL에서 응답 body를 **bytes**로 수신 (같은 프로세스 또는 별도 HTTP 클라이언트) |
| 파서 입력 | `pdf_path: str` (저장된 파일 경로) | `pdf_path_or_bytes: Union[str, bytes]` — **bytes** 전달 가능 |
| PDF 보관 | `data/{회사}_{연도}_sr.pdf`에 보관 | 보관하지 않음 (또는 필요 시 임시 파일 사용 후 삭제) |
| 결과 | `parsing_result` + 경로 반환 | 파싱 결과만 DB 테이블에 저장 |

---

## 3. 구현 상태: bytes 입력 지원

`backend.domain.shared.tool.sr_report_tools`에서 **모든 파싱 진입점**이 **경로 또는 bytes**를 받을 수 있도록 되어 있습니다.

### 3.1 공통 열기 헬퍼

```python
def _open_pdf(pdf_path_or_bytes: Union[str, bytes]):
    """파일 경로 또는 bytes로 PDF 문서를 연다. 저장 없이 메모리에서 파싱할 때 bytes 사용."""
    if isinstance(pdf_path_or_bytes, bytes):
        return fitz.open(stream=pdf_path_or_bytes, filetype="pdf")
    return fitz.open(pdf_path_or_bytes)
```

### 3.2 PDFParser

- **메서드**: `parse(self, pdf_path_or_bytes: Union[str, bytes], company: str, year: int)`
- **동작**: `str`이면 기존처럼 경로로 열고, `bytes`면 `fitz.open(stream=..., filetype="pdf")`로 열어 메타데이터·인덱스 페이지 추출.
- **반환**: `historical_sr_reports`용 dict에는 로컬 `pdf_file_path` 키를 넣지 않습니다(bytes/경로 모두).

### 3.3 파싱 진입점 (메타·인덱스·본문·이미지)

| 함수 / 모듈 | 첫 번째 인자 | 비고 |
|-------------|----------------|------|
| `parse_sr_report_metadata` | `pdf_path_or_bytes: Union[str, bytes]` | `PDFParser.parse` |
| `parse_sr_report_index` | `pdf_path_or_bytes: Union[str, bytes]` | `sr_report_tools` → Docling 표 |
| 본문 `parse_body_pages` | `pdf_bytes_b64`, `pages` | `body_parser` (Docling→LlamaParse→PyMuPDF) |
| 이미지 `extract_report_images` | `pdf_bytes`, `pages`, `output_dir`, `report_id` | `parsing.image_extractor` — 임베디드 이미지 파일 추출 + DB는 `SRImagesAgent` / `save_sr_report_images_batch` |

> **참고**: 예전 문서의 `parse_sr_report_images` 심볼은 `sr_report_tools`에 없습니다. 이미지는 위 `extract_report_images` + [SR_IMAGES_PARSING_DESIGN.md](./SR_IMAGES_PARSING_DESIGN.md) 플로우를 사용하세요.

---

## 4. 사용 예시 (bytes로 파싱)

```python
import base64
import requests
from backend.domain.shared.tool.parsing.pdf_metadata import parse_sr_report_metadata
from backend.domain.shared.tool.sr_report_tools import parse_sr_report_index
from backend.domain.shared.tool.parsing.body_parser import parse_body_pages
from backend.domain.shared.tool.parsing.image_extractor import extract_report_images

# 1) URL에서 PDF 다운로드 (저장 없이 bytes만)
url = "https://example.com/sustainability_report_2024.pdf"
resp = requests.get(url, timeout=60)
resp.raise_for_status()
pdf_bytes = resp.content

# 2) 메타데이터 추출 (historical_sr_reports 1건)
meta = parse_sr_report_metadata(pdf_bytes, company="삼성에스디에스", year=2024)
if "error" in meta:
    raise RuntimeError(meta["error"])
row = meta["historical_sr_reports"]
report_id = row["id"]
index_page_numbers = row["index_page_numbers"]
total_pages = int(row.get("total_pages") or 0)
pages = list(range(1, total_pages + 1))

# 3) 인덱스·본문·이미지 (같은 bytes 재사용)
index_result = parse_sr_report_index(pdf_bytes, report_id, index_page_numbers)
body_result = parse_body_pages(base64.b64encode(pdf_bytes).decode("utf-8"), pages)
image_result = extract_report_images(
    pdf_bytes,
    pages,
    "/tmp/sr_images",
    report_id,
    index_page_numbers=index_page_numbers,
)

# 4) DB 저장: save_* 도구 / 에이전트 (sr_report_images 는 save_sr_report_images_batch 등)
```

---

## 5. 이미지 저장 경로 (bytes 사용 시)

`extract_report_images`는 추출한 이미지를 **`output_dir` / `{report_id}` 하위**에 파일로 저장합니다.

- **`output_dir`**: 필수 (에이전트/API에서는 `SR_IMAGE_OUTPUT_DIR` 또는 요청 필드).
- 환경변수: `SR_IMAGE_MAX_EDGE`(긴 변 축소, 0=비활성), `SR_IMAGE_SKIP_INDEX_PAGES`, `SR_IMAGE_DEBUG` 등은 [SR_IMAGES_PARSING_DESIGN.md](./SR_IMAGES_PARSING_DESIGN.md) 참고.

PDF는 저장하지 않고, 이미지만 지정한 디렉터리에 저장하는 구성이 가능합니다.

---

## 6. 정리

- **저장하지 않고 다운로드만 해서 파싱하는 것**은 **가능**하며, `sr_report_tools` / `PDFParser`는 이미 **`Union[str, bytes]`** 입력을 지원합니다.
- 다운로드 단계에서 **bytes**를 넘기면 디스크에 PDF를 쓰지 않고 메모리에서만 파싱할 수 있습니다.
- 개발이 끝난 뒤에는 **다운로드 → bytes → 파싱 → DB 저장**으로 전환하면 되며, `data/`에 PDF를 남기지 않는 운영이 가능합니다.
