# ESG 데이터 통합 관리 서비스 설계

## 1. 목적

`esg_data` 서비스는 아래 두 가지를 하나의 파이프라인으로 수행한다.

1. 소스 데이터(`environmental_data`, `social_data`, `governance_data`, `company_info`)와 온톨로지(`unified_column_mappings`, `unmapped_data_points`)를 활용해 `sr_report_unified_data`를 생성/갱신
2. `data_points`, `rulebooks`, `unified_column_mappings`, `sr_report_unified_data` 간 정합성을 검사하여 이상 데이터를 탐지/리포트

핵심 목표는 "SR 보고서 생성에 필요한 통합 사실 테이블을 안정적으로 유지"하고, "매핑 누락/충돌/타입 불일치 등을 조기에 발견"하는 것이다.

---

## 2. 관리 대상 테이블

### 2.1 입력(소스) 테이블
- `environmental_data`: GHG, 에너지, 용수, 폐기물 등 환경 정량 데이터
- `social_data`: 임직원, 안전보건, 공급망, 사회공헌 데이터
- `governance_data`: 이사회, 컴플라이언스, 정보보안 데이터
- `company_info`: 회사 기본정보 및 ESG 목표/이해관계자 정보

### 2.2 온톨로지/매핑 테이블
- `data_points`: 기준서별 원천 DP 정의
- `rulebooks`: DP 중심 공시 규칙/문맥
- `unified_column_mappings`: 다중 기준서 DP를 통합 컬럼으로 매핑
- `unmapped_data_points`: 아직 UCM으로 편입되지 않은 DP

### 2.3 출력(통합) 테이블
- `sr_report_unified_data`: SR 생성용 통합 사실 테이블

---

## 3. `sr_report_unified_data` 적재 원칙

`sr_report_unified_data` 한 행은 반드시 아래 둘 중 하나의 의미 축을 가진다.

- UCM 경로: `unified_column_id` 존재, `unmapped_dp_id`는 `NULL`
- 미매핑 경로: `unmapped_dp_id` 존재, `unified_column_id`는 `NULL`

검증 규칙:
- `chk_unified_or_unmapped` (XOR) 위반 금지
- `data_type`은 `quantitative|qualitative|narrative|binary` 범위 준수
- `source_entity_type`은 정의된 소스 타입만 허용

---

## 4. 서비스 아키텍처

### 4.1 구성 컴포넌트

1. `IngestionCoordinator`
   - 회사/연도/월 범위 단위로 배치 실행
   - 소스별 로딩, 변환, 저장 단계 오케스트레이션

2. `SourceExtractors`
   - `EnvironmentalExtractor`
   - `SocialExtractor`
   - `GovernanceExtractor`
   - `CompanyInfoExtractor`
   - 역할: 각 소스 테이블 레코드를 통합용 내부 DTO로 표준화

3. `MappingResolver`
   - 내부 DTO를 `unified_column_mappings` 또는 `unmapped_data_points`에 매칭
   - 매칭 성공 시 `unified_column_id` 세팅
   - 실패 시 `unmapped_data_points` 생성/재사용 후 `unmapped_dp_id` 세팅

4. `UnifiedWriter`
   - `sr_report_unified_data` upsert
   - 키: `(company_id, period_year, period_month, source_entity_type, source_entity_id, unified_column_id|unmapped_dp_id)`

5. `DataQualityChecker`
   - 타입/단위/값 범위/매핑 정합성 검사
   - 결과를 로그/리포트 테이블/알림으로 발행

---

## 5. 처리 플로우

1. 실행 요청 수신
   - 입력: `company_id`, `period_year`, optional `period_month`, `run_mode(full|incremental|validate_only)`

2. 소스 추출
   - 4개 소스 테이블에서 해당 회사/기간 데이터 조회

3. 통합 후보 생성
   - 각 소스 행 → 통합 후보 사실(FactCandidate) 변환
   - `source_entity_type`, `source_entity_id`, `data_value`, `data_type`, `unit`, `data_source` 구성

4. 매핑 해석
   - `unified_column_mappings` 우선 매칭
   - 미매칭 시 `unmapped_data_points` 참조/생성

5. 통합 저장
   - `sr_report_unified_data` upsert
   - 필요 시 기존 행 soft-archive 혹은 버전 필드 관리

6. 이상검사 수행
   - 정합성 검사 후 요약 리포트 생성

7. 결과 반환
   - 처리 건수, 매핑 성공률, 미매핑 건수, 오류/경고 목록

---

## 6. 이상검사(Validation) 규칙

### 6.1 스키마/형식 검사
- `data_type` vs `data_value` 구조 일치 여부
  - quantitative: `{"value": number}` 권장
  - narrative: `{"text": string}` 권장
- `unit` 필수/옵션 규칙
  - quantitative는 `unit` 권장(또는 UCM 기본 단위 추론)

### 6.2 매핑 검사
- `unified_column_id` 존재 시:
  - `unified_column_mappings` 실존 여부
  - `column_type == sr_report_unified_data.data_type` 일치
  - 단위 불일치 탐지(`ucm.unit`과 상이)
- `unmapped_dp_id` 존재 시:
  - `unmapped_data_points` 실존 여부
  - `mapping_status`가 `mapped`인데 `unified_column_id`가 비어있으면 경고

### 6.3 온톨로지 정합성 검사 (`data_points`, `rulebooks` 연계)
- `unified_column_mappings.mapped_dp_ids`의 각 DP가 `data_points.dp_id`에 존재하는지
- `rulebooks.primary_dp_id` 및 관련 DP가 유효한지
- `unmapped_data_points.dp_id`가 이미 UCM의 `mapped_dp_ids`에 포함되어 있으면 중복 경고

### 6.4 데이터 품질 검사
- 중복 사실 탐지(동일 의미/동일 기간 중복)
- 값 범위 검사(`validation_rules`, `value_range`)
- 소스 최신성 검사(기간/업데이트 시각)
- 최종 보고 포함 플래그와 버전 필드 충돌 검사

---

## 7. 권장 API (초안)

### 7.1 실행 API
- `POST /api/v1/esg-data/unified/sync`
  - body: `company_id`, `period_year`, `period_month?`, `mode`
  - response: 처리 통계 + 경고/오류 요약

### 7.2 검증 API
- `POST /api/v1/esg-data/unified/validate`
  - body: `company_id`, `period_year`, `period_month?`
  - response: 검증 리포트(JSON)

### 7.3 매핑 진단 API
- `GET /api/v1/esg-data/mapping/health?company_id=...&period_year=...`
  - response: 매핑 커버리지, 미매핑 목록, 충돌 목록

---

## 8. 운영 모드

- `full`: 기간 전체 재산출
- `incremental`: 변경 소스만 반영
- `validate_only`: 저장 없이 검사만 수행

스케줄 제안:
- 일간 incremental
- 주간 full + validation
- 마감 시점 full + freeze

---

## 9. 트랜잭션/멱등성

- 회사/기간 단위 트랜잭션 경계 유지
- upsert 키를 명확히 하여 재실행 시 동일 결과 보장
- 실패 시 롤백 + 실행 로그 보존

---

## 10. 향후 확장

1. `sr_report_content`, `esg_charts`까지 같은 파이프라인으로 통합
2. `unmapped_data_points` 자동 UCM 승격 추천(LLM + 규칙 기반)
3. 품질 점수(`confidence_score`) 자동 산정
4. 검증 이력을 별도 `data_quality_issues` 테이블로 축적

---

## 11. 최소 구현 체크리스트

- [ ] 소스 추출기 4종 구현
- [ ] UCM/미매핑 해석기 구현
- [ ] `sr_report_unified_data` upsert 구현
- [ ] XOR/타입/단위 검증 구현
- [ ] `data_points`/`rulebooks`/`UCM` 정합성 점검 쿼리 구현
- [ ] 실행 리포트(JSON) 및 로그 포맷 표준화


