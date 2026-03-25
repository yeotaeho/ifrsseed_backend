# GHG 산정 및 SR 보고서 자동 작성 데이터베이스 테이블 구조

> **목적**: GHG 산정 탭, SR 보고서 자동 작성, 전년도 SR 파싱, 벤치마킹·평가, 온톨로지(통합 컬럼 매핑)에 필요한 **모든** 데이터베이스 테이블 구조를 이 문서 한 곳에 정리합니다.  
> **대상**: 개발자, 데이터베이스 설계자, 시스템 아키텍트  
> **최종 업데이트**: 2025-01-XX  
> **통합 출처**: 본 문서는 [DATA_ONTOLOGY.md](./DATA_ONTOLOGY.md)(통합 컬럼 매핑), [HISTORICAL_REPORT_PARSING.md](./HISTORICAL_REPORT_PARSING.md)(전년도 SR 파싱), [SR_REPORT_BENCHMARKING.md](./SR_REPORT_BENCHMARKING.md)(벤치마킹·평가), [AUTHENTICATION_ONPREMISE.md](./AUTHENTICATION_ONPREMISE.md)(로그인·사용자)에 흩어져 있던 테이블 정의를 통합한 단일 참조 문서입니다.

---

## 목차

1. [GHG 산정 탭 테이블](#1-ghg-산정-탭-테이블)
2. [SR 보고서 자동 작성 테이블](#2-sr-보고서-자동-작성-테이블)  
   - 2.0 통합 컬럼 매핑(온톨로지) · 2.1~2.7 환경/사회/지배구조/회사정보/본문/차트/통합데이터 · 2.8 전년도 SR 파싱 · 2.9 벤치마킹·평가
3. [테이블 간 관계 및 데이터 흐름](#3-테이블-간-관계-및-데이터-흐름) · [3.4 데이터베이스 관계 방식 정리](#34-데이터베이스-관계-방식-정리)
4. [데이터 확정 프로세스](#4-데이터-확정-프로세스)
5. [요약](#5-요약)
6. [향후 개선 사항](#6-향후-개선-사항)
7. [대시보드 및 시스템 관리 테이블](#7-대시보드-및-시스템-관리-테이블)
8. [온프레미스 로그인 및 사용자 관리 테이블](#8-온프레미스-로그인-및-사용자-관리-테이블)

---

## 1. GHG 산정 탭 테이블

### 1.1 핵심 데이터 테이블

#### `ghg_activity_data` - 활동자료 (원시 데이터)

**역할**: EMS/ERP/EHS에서 수집한 원시 활동 데이터 저장

**주요 필드**:
```sql
CREATE TABLE ghg_activity_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 탭 구분
  tab_type TEXT NOT NULL,  -- 'power_heat_steam' | 'fuel_vehicle' | 'refrigerant' | 'waste' | 'logistics_travel' | 'raw_materials'
  
  -- 기본 정보
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  -- 전력·열·스팀 (tab_type = 'power_heat_steam')
  energy_type TEXT,  -- '전력' | '열' | '스팀'
  energy_source TEXT,  -- '한국전력' | '지역난방' 등
  usage_amount DECIMAL(18, 4),
  usage_unit TEXT,  -- 'kWh' | 'Gcal' | 'GJ'
  renewable_ratio DECIMAL(5, 2),  -- 재생에너지 비율 (%)
  
  -- 연료·차량 (tab_type = 'fuel_vehicle')
  fuel_category TEXT,  -- '고정연소' | '이동연소'
  fuel_type TEXT,  -- 'LNG' | '경유' | '휘발유' 등
  consumption_amount DECIMAL(18, 4),
  fuel_unit TEXT,  -- 'Nm³' | 'L' | 'kg'
  purchase_amount DECIMAL(18, 4),
  
  -- 냉매 (tab_type = 'refrigerant')
  equipment_id TEXT,
  equipment_type TEXT,  -- '에어컨' | '냉동기' | '칠러'
  refrigerant_type TEXT,  -- 'HFC-134a' | 'HFC-410A' 등
  charge_amount_kg DECIMAL(18, 4),
  leak_amount_kg DECIMAL(18, 4),
  gwp_factor DECIMAL(18, 4),
  inspection_date DATE,
  
  -- 폐기물 (tab_type = 'waste')
  waste_type TEXT,  -- '일반' | '지정' | '건설'
  waste_name TEXT,
  generation_amount DECIMAL(18, 4),  -- 발생량 (톤)
  disposal_method TEXT,  -- '소각' | '매립' | '재활용' | '위탁'
  incineration_amount DECIMAL(18, 4),  -- 소각량 (톤)
  recycling_amount DECIMAL(18, 4),  -- 재활용량 (톤)
  
  -- 물류·출장·통근 (tab_type = 'logistics_travel')
  category TEXT,  -- '물류(인바운드)' | '물류(아웃바운드)' | '출장' | '통근'
  transport_mode TEXT,  -- '항공' | '해상' | '도로' | '철도' | '자가용'
  origin_country TEXT,
  destination_country TEXT,
  distance_km DECIMAL(18, 4),
  weight_ton DECIMAL(18, 4),  -- 물류용
  person_trips INTEGER,  -- 출장·통근용
  
  -- 원료·제품 (tab_type = 'raw_materials')
  supplier_name TEXT,
  product_name TEXT,
  supplier_emission_tco2e DECIMAL(18, 4),
  use_phase_emission DECIMAL(18, 4),
  eol_emission DECIMAL(18, 4),
  ghg_reported_yn TEXT,  -- '직접보고' | '추정'
  
  -- 데이터 품질 및 출처
  data_quality TEXT,  -- 'M1' | 'M2' | 'E1' | 'E2'
  source_system TEXT,  -- 'EMS' | 'ERP' | 'EHS' | 'SRM' | 'HR' | 'PLM' | 'manual'
  synced_at TIMESTAMPTZ,  -- 시스템 동기화 시각
  updated_at TIMESTAMPTZ,  -- 수동 수정 시각
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_ghg_activity_company (company_id, period_year, period_month),
  INDEX idx_ghg_activity_tab (company_id, tab_type)
);
```

**데이터 소스**:
- EMS: 전력·열·스팀, 폐기물
- ERP: 연료·차량
- EHS: 냉매
- SRM: 물류, 원료
- HR: 출장·통근
- PLM: 제품

**데이터 수집 방식**:
1. **내부시스템 자동 적재**: 기설정 주기(예: 매월 1일 09:00)로 자동 수집
   - EMS/ERP/EHS 시스템 API 호출 또는 파일 수집
   - 수집된 데이터는 자동으로 `ghg_activity_data`에 저장
2. **수동 불러오기**: 사용자가 "EMS 불러오기" 버튼 클릭 시 해당 시스템에서 데이터 수집
3. **엑셀 업로드**: 표준 템플릿 엑셀 파일 업로드
4. **수동 입력**: 화면에서 직접 행 추가 및 입력

**데이터 저장 구조**:
- **같은 년/월에 대해 `tab_type`별로 별도 행으로 저장됩니다**
- 예: 2024년 1월 데이터가 있다면
  - `tab_type = 'power_heat_steam'` → 1행 이상 (사업장별, 에너지원별로 세분화 가능)
  - `tab_type = 'fuel_vehicle'` → 1행 이상 (사업장별, 연료별로 세분화 가능)
  - `tab_type = 'refrigerant'` → 1행 이상 (사업장별, 설비별로 세분화 가능)
  - `tab_type = 'waste'` → 1행 이상 (사업장별, 폐기물 종류별로 세분화 가능)
  - `tab_type = 'logistics_travel'` → 1행 이상 (카테고리별로 세분화 가능)
  - `tab_type = 'raw_materials'` → 1행 이상 (공급업체별, 제품별로 세분화 가능)

**실제 저장 예시**:
```sql
-- 2024년 1월 데이터 예시
-- 행 1: 전력 데이터
id: uuid-1, company_id: 'company-001', tab_type: 'power_heat_steam', 
site_name: '서울본사', period_year: 2024, period_month: 1,
energy_type: '전력', usage_amount: 125000

-- 행 2: 열 데이터 (같은 년/월, 다른 에너지원)
id: uuid-2, company_id: 'company-001', tab_type: 'power_heat_steam',
site_name: '서울본사', period_year: 2024, period_month: 1,
energy_type: '열', usage_amount: 3200

-- 행 3: 연료 데이터 (같은 년/월, 다른 탭)
id: uuid-3, company_id: 'company-001', tab_type: 'fuel_vehicle',
site_name: '서울본사', period_year: 2024, period_month: 1,
fuel_type: 'LNG', consumption_amount: 85000

-- 행 4: 냉매 데이터 (같은 년/월, 다른 탭)
id: uuid-4, company_id: 'company-001', tab_type: 'refrigerant',
site_name: '서울본사', period_year: 2024, period_month: 1,
equipment_id: 'EQ-AC-001', leak_amount_kg: 0.8
```

**중요 사항**:
- 같은 `period_year`, `period_month`라도 `tab_type`이 다르면 **별도 행**으로 저장
- 같은 `tab_type`, `period_year`, `period_month`라도 `site_name`, `energy_type`, `fuel_type` 등이 다르면 **별도 행**으로 저장
- 즉, **한 행은 하나의 구체적인 활동 데이터**를 나타냅니다

---

#### `ghg_emission_results` - 배출량 산정 결과

**역할**: 활동자료를 배출계수와 곱해 계산한 최종 배출량 저장

**주요 필드**:
```sql
CREATE TABLE ghg_emission_results (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 기간 정보
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  -- Scope별 배출량
  scope1_total_tco2e DECIMAL(18, 4),  -- Scope 1 총 배출량
  scope1_fixed_combustion_tco2e DECIMAL(18, 4),  -- 고정연소
  scope1_mobile_combustion_tco2e DECIMAL(18, 4),  -- 이동연소
  scope1_fugitive_tco2e DECIMAL(18, 4),  -- 탈루 (냉매)
  scope1_incineration_tco2e DECIMAL(18, 4),  -- 소각
  
  scope2_location_tco2e DECIMAL(18, 4),  -- Scope 2 위치 기반
  scope2_market_tco2e DECIMAL(18, 4),  -- Scope 2 시장 기반
  scope2_renewable_tco2e DECIMAL(18, 4),  -- 재생에너지 반영
  
  scope3_total_tco2e DECIMAL(18, 4),  -- Scope 3 총 배출량
  scope3_category_1_tco2e DECIMAL(18, 4),  -- Cat.1: 구매 물품
  scope3_category_4_tco2e DECIMAL(18, 4),  -- Cat.4: 인바운드 물류
  scope3_category_6_tco2e DECIMAL(18, 4),  -- Cat.6: 출장
  scope3_category_7_tco2e DECIMAL(18, 4),  -- Cat.7: 통근
  scope3_category_9_tco2e DECIMAL(18, 4),  -- Cat.9: 아웃바운드 물류
  scope3_category_11_tco2e DECIMAL(18, 4),  -- Cat.11: 제품 사용
  scope3_category_12_tco2e DECIMAL(18, 4),  -- Cat.12: 제품 폐기
  
  total_tco2e DECIMAL(18, 4),  -- 총 배출량
  
  -- 적용 프레임워크 및 버전
  applied_framework TEXT,  -- 'GHG_Protocol' | 'IFRS_S2' | 'K-ETS' | 'GRI' | 'ESRS'
  calculation_version TEXT,  -- 'v1' | 'v2' | 'latest'
  
  -- 데이터 신뢰도
  data_quality_score DECIMAL(5, 2),  -- 0~100
  data_quality_level TEXT,  -- 'M1' | 'M2' | 'E1' | 'E2'
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_ghg_results_company (company_id, period_year),
  INDEX idx_ghg_results_framework (company_id, applied_framework)
);
```

---

#### `ghg_emission_factors` - 배출계수

**역할**: 배출계수 마스터 데이터 저장

**주요 필드**:
```sql
CREATE TABLE ghg_emission_factors (
  id UUID PRIMARY KEY,
  
  -- 배출계수 식별
  factor_code TEXT NOT NULL UNIQUE,  -- 'KR_2024_GRID_ELECTRICITY'
  factor_name_ko TEXT NOT NULL,
  factor_name_en TEXT,
  
  -- 배출계수 값
  emission_factor DECIMAL(18, 6),  -- tCO2e/단위
  unit TEXT NOT NULL,  -- 'kWh' | 'Nm³' | 'L' | 'kg' 등
  
  -- 적용 범위
  applicable_scope TEXT,  -- 'Scope1' | 'Scope2' | 'Scope3'
  applicable_category TEXT,  -- '고정연소' | '이동연소' | '전력' 등
  
  -- 기준 정보
  reference_year INTEGER,  -- 2024
  reference_source TEXT,  -- '환경부' | 'K-ETS' | 'IPCC' | 'IEA'
  reference_url TEXT,
  
  -- GWP 정보
  gwp_value DECIMAL(18, 4),  -- 지구온난화지수 (CO2=1 기준)
  
  -- 유효 기간
  effective_from DATE,
  effective_to DATE,
  
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_ghg_factors_code (factor_code),
  INDEX idx_ghg_factors_scope (applicable_scope, applicable_category)
);
```

---

#### `ghg_calculation_evidence` - 산정 근거

**역할**: 각 활동자료에 대한 산정 근거 정보를 별도로 저장 (배출계수, 산식, 산정 결과 등)

**설계 이유**:
- 활동자료(`ghg_activity_data`)는 원시 데이터만 유지
- 산정 근거는 스냅샷으로 독립 관리하여 재산정 이력 추적 가능
- 감사 추적 및 산정 근거 화면 표시에 활용

**주요 필드**:
```sql
CREATE TABLE ghg_calculation_evidence (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 연결 정보
  activity_data_id UUID NOT NULL,  -- ghg_activity_data.id 참조
  tab_type TEXT NOT NULL,  -- 'power_heat_steam' | 'fuel_vehicle' | 'refrigerant' | 'waste' | 'logistics_travel' | 'raw_materials'
  
  -- 배출계수 정보 (산정 시점 스냅샷)
  applied_factor_id TEXT,  -- 'EF-LNG-2023' | 'EF-전력-2024'
  applied_factor_value DECIMAL(18, 6),  -- 산정 시점 배출계수 값 (스냅샷)
  applied_factor_version TEXT,  -- '2023-환경부' | '2024-K-ETS'
  applied_gwp_basis TEXT,  -- 'AR5' | 'AR6'
  
  -- 산정 방법론
  calculation_method TEXT,  -- '연료연소법' | 'spend-based' | 'distance-based' | 'activity-based'
  calculation_formula TEXT,  -- 산정 산식 (텍스트) 예: '125000 × 0.0005 × 1.0'
  
  -- 산정 입력값 (활동자료 스냅샷)
  activity_amount DECIMAL(18, 4),  -- 활동자료 값 (예: 125000)
  activity_unit TEXT,  -- 활동자료 단위 (예: 'kWh' | 'Nm³' | 'L')
  
  -- 산정 결과
  ghg_emission_tco2e DECIMAL(18, 4),  -- 산정된 배출량 (tCO₂e)
  
  -- 산정 메타데이터
  calculated_at TIMESTAMPTZ NOT NULL,  -- 산정 실행 일시
  calculated_by TEXT NOT NULL,  -- 산정 실행 사용자 ID
  calculation_version TEXT,  -- 'v1' | 'v2' | 'v3' (재산정 시 증가)
  
  -- 재산정 이력 추적
  is_latest BOOLEAN DEFAULT TRUE,  -- 최신 산정 여부
  previous_evidence_id UUID,  -- 이전 산정 근거 참조 (이력 체인)
  
  -- Scope 분류 (산정 결과 연결용)
  scope_type TEXT,  -- 'Scope1' | 'Scope2' | 'Scope3'
  scope_category TEXT,  -- '고정연소' | '이동연소' | '전력' | 'Cat.1' 등
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_evidence_activity (activity_data_id),
  INDEX idx_evidence_company (company_id, calculated_at),
  INDEX idx_evidence_latest (company_id, activity_data_id, is_latest),
  INDEX idx_evidence_factor (applied_factor_id),
  INDEX idx_evidence_scope (company_id, scope_type, scope_category)
);
```

**데이터 흐름**:
```
[ghg_activity_data] 활동자료 입력
    ↓
[배출계수 조회] ghg_emission_factors
    ↓
[산정 실행]
    ↓
[ghg_calculation_evidence] 산정 근거 저장 (스냅샷)
    ↓
[ghg_emission_results] 집계 결과 저장
```

**재산정 이력 관리 예시**:
```sql
-- 1차 산정
INSERT INTO ghg_calculation_evidence (
  activity_data_id, applied_factor_id, applied_factor_value,
  calculation_formula, ghg_emission_tco2e, calculated_at,
  calculated_by, calculation_version, is_latest
)
VALUES (
  'uuid-activity-1', 'EF-전력-2024', 0.0005,
  '125000 × 0.0005', 62.5,
  '2024-02-15 10:30:00', 'user_001', 'v1', TRUE
);

-- 2차 재산정 (배출계수 변경)
INSERT INTO ghg_calculation_evidence (
  activity_data_id, applied_factor_id, applied_factor_value,
  calculation_formula, ghg_emission_tco2e, calculated_at,
  calculated_by, calculation_version, is_latest, previous_evidence_id
)
VALUES (
  'uuid-activity-1', 'EF-전력-2024', 0.0006,  -- 배출계수 변경
  '125000 × 0.0006', 75.0,  -- 재산정 결과
  '2024-02-20 14:00:00', 'user_001', 'v2',
  TRUE,  -- 최신으로 설정
  'uuid-evidence-1'  -- 이전 산정 근거 참조
);

-- 이전 산정 근거는 is_latest = FALSE로 업데이트
UPDATE ghg_calculation_evidence 
SET is_latest = FALSE 
WHERE id = 'uuid-evidence-1';
```

**사용 목적**:
- 산정 근거 화면 표시 (어떤 배출계수를 어떻게 적용했는지)
- 감사 추적 (재산정 이력, 배출계수 변경 이력)
- 데이터 계보 추적 (활동자료 → 배출계수 → 배출량)
- 배출계수 버전 불일치 경고 (현행 MDG값과 비교)

**중요 원칙**:
- `applied_factor_value`는 산정 시점 값을 **스냅샷으로 고정** 저장
- MDG 배출계수가 이후 갱신되더라도 당시 산정 근거가 보존됨
- 재산정 시에도 이전 산정 근거는 보존하고 새 레코드 생성

---

### 1.2 감사 및 버전 관리 테이블

#### `ghg_calculation_snapshots` - 산정 버전 스냅샷

**역할**: 특정 시점의 산정 결과를 버전으로 저장 (v1, v2, v3...) 및 마감 상태 관리

**설계 원칙**:
- **FK 참조**: `ghg_emission_results`의 PK를 FK로 참조하여 원본 추적
- **데이터 복사**: `payload`에 스냅샷 시점의 데이터를 복사 저장하여 원본 변경 시에도 스냅샷 값 유지
- **마감 통합**: 마감 상태를 이 테이블에서 직접 관리 (`ghg_period_locks`와 통합)

**주요 필드**:
```sql
CREATE TABLE ghg_calculation_snapshots (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 기간 정보
  period_year INTEGER NOT NULL,
  period_month INTEGER,  -- NULL이면 연간
  
  -- 버전 정보
  snapshot_version TEXT NOT NULL,  -- 'v1' | 'v2' | 'v3'
  label TEXT,  -- '2024년 1분기 최종' | '수원공장 수정 반영'
  
  -- FK 참조 (어떤 ghg_emission_results를 스냅샷으로 만든 것인지)
  emission_result_id UUID REFERENCES ghg_emission_results(id),
  
  -- 스냅샷 데이터 (시점 고정을 위해 복사 저장)
  payload JSONB NOT NULL,  -- 전체 데이터셋 (scope1, scope2, scope3, boundaryPolicy)
  -- payload 예시: {"scope1_total_tco2e": 1234.5, "scope2_location_tco2e": 567.8, ...}
  
  -- 마감 상태 (ghg_period_locks 기능 통합)
  is_locked BOOLEAN DEFAULT FALSE,  -- 마감 여부
  locked_by TEXT,  -- 마감한 사용자
  locked_at TIMESTAMPTZ,  -- 마감 시각
  lock_reason TEXT,  -- 마감 사유
  
  -- 잠금 해제 정보
  unlocked_by TEXT,
  unlocked_at TIMESTAMPTZ,
  unlock_reason TEXT,
  
  -- Scope별 잠금 (선택적)
  scope_type TEXT,  -- 'scope1' | 'scope2' | 'scope3' | 'all' (NULL이면 전체)
  
  -- 메타데이터
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_ghg_snapshots_company (company_id, period_year, period_month),
  INDEX idx_ghg_snapshots_result (emission_result_id),
  INDEX idx_ghg_snapshots_locked (company_id, is_locked, period_year),
  INDEX idx_ghg_snapshots_version (company_id, snapshot_version)
);
```

**저장 버튼 클릭 시 동작**:
```
[사용자] "이 탭 결과 저장" 또는 "전체 결과 저장" 클릭
  ↓
[시스템] 
  1. 현재 ghg_emission_results 조회
  2. 다음 버전 번호 계산 (v1 → v2 → v3...)
  3. ghg_calculation_snapshots 생성
     - emission_result_id: FK 참조 (원본 추적)
     - payload: JSONB로 데이터 복사 (시점 고정)
     - is_locked: FALSE (아직 마감 안됨)
```

**마감 버튼 클릭 시 동작**:
```
[사용자] "마감" 버튼 클릭
  ↓
[시스템] ghg_calculation_snapshots 업데이트
  - is_locked: TRUE
  - locked_by: 사용자 ID
  - locked_at: 현재 시각
  - lock_reason: 마감 사유
```

**사용 목적**:
- 버전 비교 (v1 vs v2 vs v3) - `payload`의 고정된 값으로 비교 가능
- 롤백 (특정 버전으로 되돌리기) - `payload`에서 데이터 복원
- 감사 증빙 (마감 시점 데이터 재현) - `is_locked = TRUE`인 버전 조회
- 원본 추적 - `emission_result_id`로 어떤 산정 결과를 스냅샷으로 만들었는지 추적

**중요 원칙**:
- `payload`는 스냅샷 생성 시점의 데이터를 **복사 저장**하여 원본(`ghg_emission_results`)이 이후 변경되어도 스냅샷 값은 유지됨
- `emission_result_id`는 원본 추적용으로만 사용하며, 실제 조회는 `payload` 사용

---

#### `ghg_audit_logs` - 변경 추적 로그

**역할**: 데이터 변경 이력 추적 (어떤 필드가 언제, 누가, 왜 변경되었는지)

**추적 대상 엔티티**:
- `activity_data`: 활동자료 변경 이력 (`ghg_activity_data`)
- `emission_results`: 배출량 산정 결과 변경 이력 (`ghg_emission_results`)
- `calculation_snapshots`: 산정 버전 스냅샷 생성/수정/마감 이력 (`ghg_calculation_snapshots`)

**주요 필드**:
```sql
CREATE TABLE ghg_audit_logs (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),  -- FK 추가
  
  -- 변경 대상 (Polymorphic Association)
  entity_type TEXT NOT NULL,  -- 'activity_data' | 'emission_results' | 'calculation_snapshots'
  entity_id UUID NOT NULL,  -- 해당 테이블의 PK (FK 제약조건은 걸 수 없음)
  
  -- 변경 정보
  action TEXT NOT NULL,  -- 'insert' | 'update' | 'delete'
  old_value JSONB,  -- 변경 전 값 (변경된 필드만)
  new_value JSONB,  -- 변경 후 값 (변경된 필드만)
  
  -- 변경자 정보 (users 테이블 FK)
  changed_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,  -- TEXT → UUID로 변경, FK 추가
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  change_reason TEXT,  -- 'ERP 데이터 오류 정정' | '현장 확인 후 수정' | '마감 처리' | '잠금 해제'
  
  -- 트리거 정보
  triggered_by TEXT,  -- 'api' | 'trigger' | 'manual'
  
  INDEX idx_ghg_audit_entity (entity_type, entity_id),
  INDEX idx_ghg_audit_company (company_id, changed_at),
  INDEX idx_ghg_audit_user (changed_by, changed_at),  -- 사용자별 조회용 인덱스 추가
  
  -- 제약조건
  CONSTRAINT chk_entity_type CHECK (
    entity_type IN ('activity_data', 'emission_results', 'calculation_snapshots')
  ),
  CONSTRAINT chk_action CHECK (
    action IN ('insert', 'update', 'delete')
  )
);
```

**사용 목적**:
- 수동 수정 감지
- 감사인 질의 대응
- 필드별 변경 추적
- **마감/해제 이력 추적** (`ghg_calculation_snapshots`의 `is_locked` 변경)
- **버전 생성 이력 추적** (`ghg_calculation_snapshots`의 INSERT)

**특히 중요한 추적 사항** (`calculation_snapshots`):
- 버전 생성 시점 및 생성자
- 마감 처리 시점, 처리자, 사유 (`is_locked: FALSE → TRUE`)
- 잠금 해제 시점, 해제자, 사유 (`is_locked: TRUE → FALSE`)
- label 또는 payload 수정 이력

**참조 무결성**:
- `changed_by`: `users.id`를 참조하며, `ON DELETE RESTRICT`로 설정하여 사용자 삭제 시 감사 로그가 있으면 삭제를 막아 감사 추적 보존
- `company_id`: `companies.id`를 참조하여 회사별 조회 성능 향상 및 참조 무결성 보장
- `entity_id`: Polymorphic Association이므로 DB 레벨 FK 제약조건은 걸 수 없으나, 애플리케이션 레벨에서 검증 필요

---

### 1.3 승인 및 잠금 관리 테이블

#### `ghg_period_locks` - 기간별 데이터 잠금

**역할**: 특정 기간의 데이터를 마감하여 수정 불가 상태로 설정

**참고**: 마감 기능은 `ghg_calculation_snapshots` 테이블에 통합되었습니다 (`is_locked`, `locked_by`, `locked_at` 필드).  
이 테이블은 **기존 시스템과의 호환성** 또는 **세부적인 잠금 관리**가 필요한 경우에만 사용할 수 있습니다.

**주요 필드**:
```sql
CREATE TABLE ghg_period_locks (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 잠금 대상
  period_year INTEGER NOT NULL,
  period_month INTEGER,  -- NULL이면 연간 잠금
  scope_type TEXT,  -- 'scope1' | 'scope2' | 'scope3' | 'all'
  
  -- 잠금 상태
  status TEXT NOT NULL,  -- 'locked' | 'unlocked'
  locked_by TEXT NOT NULL,
  locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lock_reason TEXT,
  
  -- 잠금 해제 정보
  unlocked_by TEXT,
  unlocked_at TIMESTAMPTZ,
  unlock_reason TEXT,
  
  INDEX idx_ghg_locks_company (company_id, period_year, period_month)
);
```

**권장 사용 방식**:
- **옵션 1 (권장)**: `ghg_calculation_snapshots`의 마감 기능만 사용
  - 마감 시 `ghg_calculation_snapshots.is_locked = TRUE`로 설정
  - 이 테이블은 사용하지 않음
  
- **옵션 2**: 두 테이블 모두 사용 (세부 관리 필요 시)
  - `ghg_calculation_snapshots`: 버전별 스냅샷 및 마감 상태
  - `ghg_period_locks`: 기간별 잠금 상태 (스냅샷과 독립적으로 관리)

---

#### `ghg_unlock_requests` - 잠금 해제 요청 (레거시)

**역할**: 잠금된 데이터 수정을 위한 해제 요청

**⚠️ 통합 계획**: 이 테이블은 `workflow_approvals` 테이블로 통합 예정입니다.  
새로운 잠금 해제 요청 기능은 `workflow_approvals` 테이블을 사용하시기 바랍니다 (`workflow_type = 'ghg_unlock'`).

**기존 테이블의 한계**:
- 단일 승인자만 지원 (`approved_by` 필드)
- 다단계 승인 프로세스 지원 불가
- 다른 승인 워크플로우와 분리되어 코드 중복 발생

**통합 후 장점**:
- 다단계 승인 지원 (검토자 → 승인자)
- 모든 승인 워크플로우를 하나의 테이블로 통합 관리
- 일관된 승인 프로세스 및 코드 중복 제거
- e-Sign 지원 (`workflow_approval_steps` 테이블 활용)

**주요 필드**:
```sql
CREATE TABLE ghg_unlock_requests (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 요청 대상
  period_lock_id UUID NOT NULL REFERENCES ghg_period_locks(id),
  
  -- 요청 정보
  requested_by TEXT NOT NULL,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason TEXT NOT NULL,  -- '데이터 오류 정정' | '추가 데이터 입력'
  
  -- 승인 상태
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  approval_comment TEXT,
  
  INDEX idx_ghg_unlock_requests_company (company_id, status)
);
```

**마이그레이션 전략**:
```sql
-- 기존 ghg_unlock_requests 데이터를 workflow_approvals로 마이그레이션
INSERT INTO workflow_approvals (
  company_id,
  workflow_type,  -- 'ghg_unlock'
  workflow_category,  -- 'ghg'
  workflow_name,  -- 'GHG 잠금 해제 요청'
  related_entity_type,  -- 'ghg_calculation_snapshots'
  related_entity_id,  -- period_lock_id에서 변환 (실제 스냅샷 ID)
  requested_by,
  request_message,  -- reason
  status,  -- pending → pending, approved → approved, rejected → rejected
  total_steps,  -- 1 (단일 승인자)
  approvers,  -- JSONB로 변환
  completed_at,  -- approved_at
  completed_by,  -- approved_by
  completion_message  -- approval_comment
)
SELECT 
  ur.company_id,
  'ghg_unlock' AS workflow_type,
  'ghg' AS workflow_category,
  'GHG 잠금 해제 요청' AS workflow_name,
  'ghg_calculation_snapshots' AS related_entity_type,
  -- period_lock_id에서 실제 스냅샷 ID로 변환
  (SELECT id FROM ghg_calculation_snapshots 
   WHERE company_id = ur.company_id 
   AND period_year = pl.period_year 
   AND period_month = pl.period_month 
   AND is_locked = TRUE
   ORDER BY locked_at DESC
   LIMIT 1) AS related_entity_id,
  ur.requested_by::UUID,  -- TEXT → UUID 변환
  ur.reason AS request_message,
  CASE ur.status
    WHEN 'pending' THEN 'pending'
    WHEN 'approved' THEN 'approved'
    WHEN 'rejected' THEN 'rejected'
  END AS status,
  1 AS total_steps,  -- 단일 승인자
  jsonb_build_array(
    CASE WHEN ur.approved_by IS NOT NULL
      THEN jsonb_build_object(
        'user_id', ur.approved_by::UUID,
        'step', 1,
        'role', 'approver',
        'status', CASE ur.status
          WHEN 'pending' THEN 'pending'
          WHEN 'approved' THEN 'approved'
          WHEN 'rejected' THEN 'rejected'
        END,
        'action', CASE ur.status
          WHEN 'approved' THEN 'approved'
          WHEN 'rejected' THEN 'rejected'
          ELSE NULL
        END,
        'comment', ur.approval_comment,
        'action_at', ur.approved_at
      )
      ELSE NULL
    END
  ) AS approvers,
  ur.approved_at AS completed_at,
  ur.approved_by::UUID AS completed_by,
  ur.approval_comment AS completion_message
FROM ghg_unlock_requests ur
LEFT JOIN ghg_period_locks pl ON ur.period_lock_id = pl.id;
```

---

#### `ghg_approval_workflows` - 승인 워크플로우 (레거시)

**역할**: 다단계 승인 프로세스 관리

**⚠️ 통합 계획**: 이 테이블은 `workflow_approvals` 테이블로 통합 예정입니다.  
새로운 승인 워크플로우는 `workflow_approvals` 테이블을 사용하시기 바랍니다.

**주요 필드**:
```sql
CREATE TABLE ghg_approval_workflows (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 워크플로우 정보
  workflow_type TEXT NOT NULL,  -- 'unlock' | 'data_submission' | 'final_approval'
  target_id UUID NOT NULL,  -- unlock_request_id 등
  
  -- 진행 상태
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'approved' | 'rejected'
  current_step INTEGER DEFAULT 1,  -- 현재 단계 (1, 2, 3...)
  total_steps INTEGER DEFAULT 2,  -- 총 단계 수
  
  -- 승인자 정보
  approver_1_id TEXT,  -- 검토자
  approver_2_id TEXT,  -- 승인자 (팀장)
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  
  INDEX idx_ghg_workflows_company (company_id, status)
);
```

**기존 테이블의 한계**:
- GHG 전용으로 설계되어 확장성 부족
- 2단계만 지원 (approver_1, approver_2 하드코딩)
- `target_id`가 무엇을 가리키는지 불명확
- TEXT 타입 사용 (FK 제약조건 없음)

**통합 후 장점**:
- 모든 승인 워크플로우를 하나의 테이블로 통합 관리
- 다단계 승인 지원 (JSONB로 유연하게)
- Polymorphic Association으로 다양한 엔티티 타입 지원
- 코드 중복 제거 및 유지보수 용이

---

#### `ghg_approval_steps` - 승인 단계별 상세 (레거시)

**역할**: 각 승인 단계의 상세 정보 및 e-Sign

**⚠️ 통합 계획**: 이 테이블은 `workflow_approval_steps` 테이블로 통합 예정입니다.

**주요 필드**:
```sql
CREATE TABLE ghg_approval_steps (
  id UUID PRIMARY KEY,
  workflow_id UUID NOT NULL REFERENCES ghg_approval_workflows(id),
  
  -- 단계 정보
  step_order INTEGER NOT NULL,  -- 1, 2, 3...
  approver_role TEXT NOT NULL,  -- 'reviewer' | 'approver'
  approver_id TEXT NOT NULL,
  
  -- 승인 정보
  action TEXT NOT NULL,  -- 'approved' | 'rejected'
  comment TEXT,
  signed_at TIMESTAMPTZ,
  
  -- e-Sign 정보
  e_sign_data JSONB,  -- {signerId, timestamp, hash}
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_ghg_steps_workflow (workflow_id, step_order)
);
```

---

### 1.4 증빙 및 공시 요건 테이블

#### `ghg_evidence_files` - 증빙 파일

**역할**: 산정 근거 자료 (영수증, 측정 기록 등) 저장

**주요 필드**:
```sql
CREATE TABLE ghg_evidence_files (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 연결 정보
  related_entity_type TEXT NOT NULL,  -- 'activity_data' | 'emission_results'
  related_entity_id UUID NOT NULL,
  
  -- 파일 정보
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  file_type TEXT,  -- 'pdf' | 'excel' | 'image'
  file_size BIGINT,  -- bytes
  
  -- 무결성 검증
  sha256_hash TEXT NOT NULL,  -- 파일 해시
  
  -- 메타데이터
  uploaded_by TEXT NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  description TEXT,
  
  INDEX idx_ghg_evidence_entity (related_entity_type, related_entity_id)
);
```

**사용 목적**:
- 감사 증빙 (모든 Scope)
- 데이터 무결성 검증
- 공시 제출 (리포트 생성 시 증빙 패키지 포함)

---

#### `ghg_audit_comments` - 감사 코멘트 (레거시)

**역할**: 감사인/검증인 코멘트 저장

**⚠️ 통합 계획**: 이 테이블은 `comments` 범용 코멘트 테이블로 통합 예정입니다.  
새로운 코멘트 기능은 `comments` 테이블을 사용하시기 바랍니다.

**주요 필드**:
```sql
CREATE TABLE ghg_audit_comments (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 연결 정보
  related_entity_type TEXT NOT NULL,
  related_entity_id UUID NOT NULL,
  
  -- 코멘트 정보
  comment_text TEXT NOT NULL,
  comment_type TEXT,  -- 'question' | 'finding' | 'recommendation'
  
  -- 작성자 정보
  commented_by TEXT NOT NULL,
  commented_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- 응답 정보
  response_text TEXT,
  responded_by TEXT,
  responded_at TIMESTAMPTZ,
  
  INDEX idx_ghg_comments_entity (related_entity_type, related_entity_id)
);
```

**기존 테이블의 한계**:
- GHG 전용으로 설계되어 확장성 부족
- 스레드 형태 질의응답 미지원 (1:1 구조만)
- TEXT 타입 사용 (FK 제약조건 없음)
- `review_requests`와 기능 중복

**통합 후 장점**:
- 모든 코멘트를 하나의 테이블로 통합 관리
- 스레드 형태 질의응답 지원
- 다양한 엔티티 타입 지원 (Polymorphic Association)
- 코드 중복 제거 및 유지보수 용이

---

#### `ghg_disclosure_requirements` - 공시 요건 체크리스트

**역할**: 프레임워크별 공시 요건 충족 여부 추적

**주요 필드**:
```sql
CREATE TABLE ghg_disclosure_requirements (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- 프레임워크 정보
  framework TEXT NOT NULL,  -- 'IFRS_S2' | 'K-ETS' | 'GRI' | 'ESRS'
  requirement_code TEXT NOT NULL,  -- 'S2-29-a' | 'KETS-MONTHLY-ENERGY'
  requirement_name_ko TEXT NOT NULL,
  requirement_name_en TEXT,
  
  -- 충족 여부
  is_fulfilled BOOLEAN DEFAULT FALSE,
  fulfillment_evidence TEXT,  -- 'ghg_emission_results.id=123'
  fulfillment_date DATE,
  
  -- 자동 체크 로직
  auto_check_query TEXT,  -- 자동 체크 SQL 또는 로직
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_ghg_requirements_company (company_id, framework),
  INDEX idx_ghg_requirements_fulfilled (company_id, is_fulfilled)
);
```

**사용 목적**:
- 프레임워크별 요건 자동 체크
- 미충족 항목 명확히 파악
- 공시 준수율 계산

---

## 2. SR 보고서 자동 작성 테이블

### 2.0 통합 컬럼 매핑 테이블 (온톨로지)

여러 기준서(IFRS S2, GRI, TCFD 등)의 동일한 의미를 가진 Data Point를 하나의 통합 컬럼으로 묶어 관리합니다. `sr_report_unified_data`는 **매핑된** 행에서 이 테이블을 FK로 참조하고, **아직 통합 컬럼에 올리지 않은 DP**는 `unmapped_data_points`를 FK로 참조합니다(두 FK는 상호 배타). 상세 설계는 [DATA_ONTOLOGY.md](./DATA_ONTOLOGY.md)를 참조하세요.

#### `unified_column_mappings` - 통합 컬럼 매핑

**역할**: 기준서에 종속되지 않는 중립적 통합 컬럼 정의 및 다중 기준서 DP 매핑

**주요 필드**:
```sql
CREATE TABLE unified_column_mappings (
    -- 식별자 및 기본 정보
    unified_column_id VARCHAR(50) PRIMARY KEY,  -- 예: "001_aa", "002_ab"
    column_name_ko VARCHAR(200) NOT NULL,
    column_name_en VARCHAR(200) NOT NULL,
    column_description TEXT,  -- 통합 컬럼 상세 설명
    
    -- 분류 정보 (조인 없이 빠른 조회용)
    column_category CHAR(1) NOT NULL CHECK (column_category IN ('E', 'S', 'G')),
    column_topic VARCHAR(100),
    column_subtopic VARCHAR(100),
    
    -- 매핑 정보 (핵심)
    mapped_dp_ids TEXT[] NOT NULL,  -- 여러 기준서의 DP 배열 (예: ['IFRS_S2-S2-29-a', 'GRI-305-1'])
    
    -- 데이터 타입 정보
    column_type VARCHAR(20) NOT NULL CHECK (column_type IN ('quantitative', 'qualitative', 'narrative', 'binary')),
    unit VARCHAR(50),
    
    -- 검증 규칙 (Supervisor 검증용)
    validation_rules JSONB DEFAULT '{}',
    value_range JSONB,
    
    -- 재무 연결 (Gen Node 재무 영향 문단 생성용)
    financial_linkages TEXT[],
    financial_impact_type VARCHAR(50),  -- 'positive' | 'negative' | 'neutral'
    
    -- 공시 요구사항
    disclosure_requirement VARCHAR(20) CHECK (disclosure_requirement IN ('필수', '권장', '선택')),
    reporting_frequency VARCHAR(20),  -- 연간, 분기별, 반기별 등
    
    -- 임베딩 (벡터 검색용, pgvector)
    unified_embedding vector(1024),
    
    -- 메타데이터
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

### 2.1 환경 데이터 테이블

#### `environmental_data` - 환경 데이터 통합

**역할**: GHG 배출량, 에너지, 용수, 폐기물, 대기 배출 데이터 통합 저장

**주요 필드**:
```sql
CREATE TABLE environmental_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  -- ===== GHG 배출량 (ghg_emission_results에서 가져오기) =====
  scope1_total_tco2e DECIMAL(18, 4),
  scope2_location_tco2e DECIMAL(18, 4),
  scope2_market_tco2e DECIMAL(18, 4),
  scope3_total_tco2e DECIMAL(18, 4),
  
  -- ===== 에너지 (ghg_activity_data에서 집계) =====
  total_energy_consumption_mwh DECIMAL(18, 4),  -- 총 에너지 소비량
  renewable_energy_mwh DECIMAL(18, 4),  -- 재생에너지 사용량
  renewable_energy_ratio DECIMAL(5, 2),  -- 재생에너지 비율 (%)
  
  -- ===== 폐기물 (ghg_activity_data에서 집계) =====
  total_waste_generated DECIMAL(18, 4),  -- 총 폐기물 발생량
  waste_recycled DECIMAL(18, 4),  -- 재활용량
  waste_incinerated DECIMAL(18, 4),  -- 소각량
  waste_landfilled DECIMAL(18, 4),  -- 매립량
  hazardous_waste DECIMAL(18, 4),  -- 유해폐기물
  
  -- ===== 용수 (별도 수집 필요) =====
  water_withdrawal DECIMAL(18, 4),  -- 용수 취수량 (톤)
  water_consumption DECIMAL(18, 4),  -- 용수 사용량 (톤)
  water_discharge DECIMAL(18, 4),  -- 폐수 방류량 (톤)
  water_recycling DECIMAL(18, 4),  -- 용수 재활용량 (톤)
  
  -- ===== 대기 배출 (별도 수집 필요) =====
  nox_emission DECIMAL(18, 4),  -- NOx 배출량
  sox_emission DECIMAL(18, 4),  -- SOx 배출량
  voc_emission DECIMAL(18, 4),  -- VOC 배출량
  dust_emission DECIMAL(18, 4),  -- 먼지 배출량 (TSP)
  
  -- ===== 환경 인증 =====
  iso14001_certified BOOLEAN,
  iso14001_cert_date DATE,
  carbon_neutral_certified BOOLEAN,
  carbon_neutral_cert_date DATE,
  
  -- ===== 데이터 소스 추적 =====
  ghg_data_source TEXT,  -- 'ghg_emission_results' | 'ghg_activity_data' | 'manual' | 'erp' | 'ems'
  ghg_calculation_version TEXT,  -- GHG 산정 버전
  
  -- ===== 승인 상태 =====
  status TEXT DEFAULT 'draft',  -- 'draft' | 'pending_review' | 'approved' | 'rejected' | 'final_approved'
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  final_approved_at TIMESTAMPTZ,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_env_company (company_id, period_year),
  INDEX idx_env_status (company_id, status)
);
```

**데이터 소스**:
- GHG 배출량: `ghg_emission_results`에서 자동 가져오기
- 에너지/폐기물: `ghg_activity_data`에서 집계
- 용수/대기: 별도 입력 또는 ERP/EMS 연동

---

### 2.2 사회 데이터 테이블

#### `social_data` - 사회 데이터 통합

**역할**: 임직원, 안전보건, 협력회사, 사회공헌 데이터 저장

**주요 필드**:
```sql
CREATE TABLE social_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  data_type TEXT NOT NULL,  -- 'workforce' | 'safety' | 'supply_chain' | 'community'
  period_year INTEGER NOT NULL,
  
  -- ===== 인력 구성 =====
  total_employees INTEGER,  -- 총 임직원 수
  male_employees INTEGER,  -- 남성 임직원 수
  female_employees INTEGER,  -- 여성 임직원 수
  disabled_employees INTEGER,  -- 장애인 임직원 수
  average_age DECIMAL(5, 2),  -- 평균 연령
  turnover_rate DECIMAL(5, 2),  -- 이직률 (%)
  
  -- ===== 안전보건 =====
  total_incidents INTEGER,  -- 총 산업재해 건수
  fatal_incidents INTEGER,  -- 사망 사고 건수
  lost_time_injury_rate DECIMAL(5, 2),  -- LTIFR
  total_recordable_injury_rate DECIMAL(5, 2),  -- TRIR
  safety_training_hours DECIMAL(10, 2),  -- 안전교육 시간
  
  -- ===== 협력회사 =====
  total_suppliers INTEGER,  -- 총 협력사 수
  supplier_purchase_amount DECIMAL(18, 2),  -- 협력사 구매액
  esg_evaluated_suppliers INTEGER,  -- ESG 평가 협력사 수
  
  -- ===== 사회공헌 =====
  social_contribution_cost DECIMAL(18, 2),  -- 사회공헌 활동 비용
  volunteer_hours DECIMAL(10, 2),  -- 봉사활동 시간
  
  -- ===== 승인 상태 =====
  status TEXT DEFAULT 'draft',  -- 'draft' | 'pending_review' | 'approved' | 'rejected' | 'final_approved'
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  final_approved_at TIMESTAMPTZ,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_social_company (company_id, period_year),
  INDEX idx_social_status (company_id, status)
);
```

**데이터 소스**:
- HR 시스템 (임직원, 안전보건)
- SRM 시스템 (협력회사)
- 수동 입력 (사회공헌)

**스테이징 → social_data 변환**: `social_data`는 회사·기간당 **1행**이므로, 스테이징 테이블(`staging_hr_data`, `staging_srm_data`, 필요 시 `staging_ehs_data`)에서 파싱한 결과를 **같은 키(company_id, period_year)로 JOIN**하여 한 행을 조립한 뒤 적재합니다. **UNION ALL이 아닌 JOIN**을 사용합니다. 상세는 [6.3 권장 개선 구조](#63-권장-개선-구조) 내 "스테이징 → social_data 변환: CTE + JOIN" 참고.

---

### 2.3 지배구조 데이터 테이블

#### `governance_data` - 지배구조 데이터 통합

**역할**: 이사회, 컴플라이언스, 정보보안 데이터 저장

**주요 필드**:
```sql
CREATE TABLE governance_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  data_type TEXT NOT NULL,  -- 'board' | 'compliance' | 'ethics' | 'risk'
  period_year INTEGER NOT NULL,
  
  -- ===== 이사회 =====
  total_board_members INTEGER,  -- 총 이사 수
  female_board_members INTEGER,  -- 여성 이사 수
  board_meetings INTEGER,  -- 이사회 개최 수
  board_attendance_rate DECIMAL(5, 2),  -- 출석률 (%)
  board_compensation DECIMAL(18, 2),  -- 이사 보수 합계
  
  -- ===== 컴플라이언스/부패 =====
  corruption_cases INTEGER,  -- 부정부패 발생 건수
  corruption_reports INTEGER,  -- 부정부패 제보 건수
  legal_sanctions INTEGER,  -- 법적 제재 건수
  
  -- ===== 정보보안 =====
  security_incidents INTEGER,  -- 정보보안 사고 건수
  data_breaches INTEGER,  -- 데이터 누출 건수
  security_fines DECIMAL(18, 2),  -- 벌금/과태료
  
  -- ===== 승인 상태 =====
  status TEXT DEFAULT 'draft',  -- 'draft' | 'pending_review' | 'approved' | 'rejected' | 'final_approved'
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  final_approved_at TIMESTAMPTZ,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_gov_company (company_id, period_year),
  INDEX idx_gov_status (company_id, status)
);
```

**데이터 소스**:
- 별도 시스템 (이사회, 컴플라이언스)
- 수동 입력

---

### 2.4 회사정보 테이블

#### `company_info` - 회사 기본정보

**역할**: 회사 기본정보, ESG 목표, 이해관계자 정보 저장

**주요 필드**:
```sql
CREATE TABLE company_info (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL UNIQUE,
  
  -- ===== 기본정보 =====
  company_name_ko TEXT NOT NULL,
  company_name_en TEXT,
  business_registration_number TEXT,
  representative_name TEXT,
  industry TEXT,
  
  -- ===== 연락처 =====
  address TEXT,
  phone TEXT,
  email TEXT,
  website TEXT,
  
  -- ===== ESG 목표 =====
  mission TEXT,
  vision TEXT,
  esg_goals JSONB,  -- ESG 핵심 목표 목록
  carbon_neutral_target_year INTEGER,  -- 탄소중립 목표 연도
  
  -- ===== 이해관계자 =====
  total_employees INTEGER,
  major_shareholders JSONB,  -- 주요 주주 목록
  stakeholders JSONB,  -- 기타 이해관계자
  
  -- ===== 최종보고서 제출 여부 =====
  submitted_to_final_report BOOLEAN DEFAULT FALSE,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**확정 조건**: "최종 보고서에 제출" 버튼 클릭 시 `submitted_to_final_report = TRUE`

---

### 2.5 SR 보고서 본문 테이블

#### `sr_report_content` - SR 보고서 문단/본문

**역할**: SR 보고서 목차별 문단 텍스트 저장

**주요 필드**:
```sql
CREATE TABLE sr_report_content (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- ===== 목차 정보 =====
  table_of_contents_id TEXT NOT NULL,  -- 목차 항목 ID
  section_title TEXT NOT NULL,
  page_number INTEGER,
  
  -- ===== 본문 내용 =====
  content_text TEXT NOT NULL,  -- 문단 텍스트
  content_type TEXT,  -- 'narrative' | 'quantitative' | 'mixed'
  
  -- ===== 공시 기준 연결 =====
  related_standards TEXT[],  -- ['IFRS_S2', 'GRI-305-1']
  related_dp_ids TEXT[],  -- ['S2-29-a', 'GRI-305-1']
  
  -- ===== 정량 데이터 (GHG 등) =====
  quantitative_data JSONB,  -- {"scope1_emission": 1234.5, ...}
  
  -- ===== 메타데이터 =====
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- ===== 최종보고서 포함 여부 =====
  saved_to_final_report BOOLEAN DEFAULT FALSE,
  
  INDEX idx_content_company (company_id, table_of_contents_id),
  INDEX idx_content_final_report (company_id, saved_to_final_report)
);
```

**확정 조건**: "저장" 또는 "최종보고서에 저장" 클릭 시 `saved_to_final_report = TRUE`

---

### 2.6 차트/도표 테이블

#### `esg_charts` - 차트/도표 데이터

**역할**: 차트/도표 데이터 및 이미지 저장

**주요 필드**:
```sql
CREATE TABLE esg_charts (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  
  -- ===== 차트 정보 =====
  chart_type TEXT NOT NULL,  -- 'bar' | 'pie' | 'line' | 'table'
  chart_category TEXT,  -- 'environmental' | 'social' | 'governance'
  chart_title TEXT NOT NULL,
  
  -- ===== 차트 데이터 =====
  chart_data JSONB NOT NULL,  -- 차트 시리즈 데이터
  chart_config JSONB,  -- 차트 설정 (색상, 범례 등)
  
  -- ===== 이미지 (생성된 차트) =====
  chart_image_url TEXT,  -- 차트 이미지 URL
  
  -- ===== 최종보고서 포함 여부 =====
  saved_to_final_report BOOLEAN DEFAULT FALSE,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_charts_company (company_id, chart_category),
  INDEX idx_charts_final_report (company_id, saved_to_final_report)
);
```

**확정 조건**: "저장" 버튼 클릭 시 `saved_to_final_report = TRUE`

---

### 2.7 SR 보고서 통합 데이터 테이블

통합 사실(`sr_report_unified_data`)은 **(A) 통합 컬럼(온톨로지)** 경로와 **(B) 아직 `unified_column_mappings`에 없는 DP** 경로 중 **하나만** 가집니다.  
`(unified_column_id IS NOT NULL AND unmapped_dp_id IS NULL)` **또는** `(unified_column_id IS NULL AND unmapped_dp_id IS NOT NULL)` 를 DB CHECK로 강제한다.

#### `unmapped_data_points` - 미매핑 Data Point

**역할**: `data_points`에 존재하거나 공시 계획상 필요하지만, 아직 `unified_column_mappings`에 편입되지 않은 DP를 한 행으로 보관한다.  
`data_points`의 핵심 메타(`dp_id`, 분류, 타입, 검증/공시 정보)를 유지하고, 이후 UCM 편입 시 후보/상태를 추적한다. `sr_report_unified_data`의 미매핑 경로에서 FK로 참조한다.

**주요 필드**:
```sql
CREATE TABLE unmapped_data_points (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- ===== data_points 정합 필드 =====
  dp_id TEXT NOT NULL,                     -- data_points.dp_id와 동일 식별자
  dp_code TEXT,                            -- data_points.dp_code
  standard_code VARCHAR(50) NOT NULL,      -- 예: 'IFRS_S2', 'GRI'
  name_ko VARCHAR(200) NOT NULL,
  name_en VARCHAR(200) NOT NULL,
  description TEXT,

  -- ===== 분류 정보 (DataPoint / UCM 공통 축) =====
  category CHAR(1) NOT NULL CHECK (category IN ('E', 'S', 'G')),
  topic VARCHAR(100),
  subtopic VARCHAR(100),

  -- ===== 데이터 타입 / 단위 =====
  dp_type VARCHAR(20) NOT NULL
    CHECK (dp_type IN ('quantitative', 'qualitative', 'narrative', 'binary')),
  unit VARCHAR(50),

  -- ===== 검증 / 공시 요구사항 (data_points, UCM과 동일 의미) =====
  validation_rules JSONB DEFAULT '[]'::jsonb,
  value_range JSONB,
  disclosure_requirement VARCHAR(20)
    CHECK (disclosure_requirement IN ('필수', '권장', '선택')),
  reporting_frequency VARCHAR(20),

  -- ===== UCM 편입 추적 =====
  candidate_unified_column_id VARCHAR(50) REFERENCES unified_column_mappings(unified_column_id),
  mapping_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (mapping_status IN ('pending', 'reviewing', 'mapped', 'rejected', 'deferred')),
  mapping_confidence DECIMAL(5, 2),         -- 0~100
  mapping_notes TEXT,
  mapped_at TIMESTAMPTZ,
  mapped_by UUID REFERENCES users(id),

  -- ===== 운영 메타 =====
  is_active BOOLEAN DEFAULT TRUE,
  source_type TEXT DEFAULT 'data_points',   -- 'data_points' | 'manual' | 'ingestion'
  source_ref_id TEXT,                       -- 원천 식별자(선택)
  notes TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (standard_code, dp_id),

  INDEX idx_unmapped_dp_id (dp_id),
  INDEX idx_unmapped_standard (standard_code),
  INDEX idx_unmapped_category_topic (category, topic),
  INDEX idx_unmapped_type (dp_type),
  INDEX idx_unmapped_status (mapping_status),
  INDEX idx_unmapped_candidate_ucm (candidate_unified_column_id)
);
```

#### `sr_report_unified_data` - SR 보고서 통합 데이터

**역할**: SR 보고서 작성에 필요한 6개 테이블(`environmental_data`, `social_data`, `governance_data`, `company_info`, `sr_report_content`, `esg_charts`)의 데이터를 통합한다.  
- **UCM 경로**: `unified_column_mappings`와 연결해 기준서별(IFRS S2, GRI 등) Data Point에 연결  
- **미매핑 경로**: `unmapped_data_points`와 연결해 아직 통합 컬럼이 없는 DP에 대한 사실을 저장

**설계 목적**:
- 여러 소스 테이블의 데이터를 하나의 통합 테이블로 집약
- `unified_column_mappings`를 통해 다중 기준서(IFRS S2, GRI, TCFD 등)의 Data Point와 매핑(UCM 행)
- 온톨로지에 없는 DP도 `unmapped_data_points`로 동일 테이블에 적재 가능(미매핑 행)
- SR 보고서 생성 시 기준서별로 필요한 데이터를 효율적으로 조회

**주요 필드**:
```sql
CREATE TABLE sr_report_unified_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  period_year INTEGER NOT NULL,
  period_month INTEGER,  -- NULL이면 연간
  
  -- ===== 소스 테이블 참조 (Polymorphic Association) =====
  source_entity_type TEXT NOT NULL,  -- 'environmental' | 'social' | 'governance' | 'company_info' | 'content' | 'chart'
  source_entity_id UUID NOT NULL,  -- 원본 테이블의 PK
  
  -- ===== 의미 축: UCM XOR 미매핑 DP (둘 중 하나만 NOT NULL) =====
  unified_column_id VARCHAR(50) REFERENCES unified_column_mappings(unified_column_id),
  unmapped_dp_id UUID REFERENCES unmapped_data_points(id),
  
  -- ===== 데이터 값 (JSONB로 유연하게 저장) =====
  data_value JSONB NOT NULL,  -- 실제 데이터 값
  -- 예시: {"value": 1234.5, "unit": "tCO2e"} 또는 {"text": "문단 내용..."}
  
  -- ===== 데이터 타입 =====
  data_type TEXT NOT NULL,  -- 'quantitative' | 'qualitative' | 'narrative' | 'binary'
  unit TEXT,  -- 단위 (quantitative인 경우)
  
  -- ===== 메타데이터 =====
  data_source TEXT,  -- 'ghg_emission_results' | 'ghg_activity_data' | 'hr' | 'manual' 등
  calculation_method TEXT,  -- 산정 방법 (GHG인 경우)
  confidence_score DECIMAL(5, 2),  -- 데이터 신뢰도 (0~100)
  
  -- ===== 최종보고서 포함 여부 =====
  included_in_final_report BOOLEAN DEFAULT FALSE,
  final_report_version TEXT,  -- 'v1' | 'v2' 등
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- 인덱스
  INDEX idx_sr_unified_company (company_id, period_year),
  INDEX idx_sr_unified_column (unified_column_id),
  INDEX idx_sr_unified_unmapped (unmapped_dp_id),
  INDEX idx_sr_unified_source (source_entity_type, source_entity_id),
  INDEX idx_sr_unified_final (company_id, included_in_final_report),
  
  -- 제약조건
  CONSTRAINT chk_source_entity_type CHECK (
    source_entity_type IN ('environmental', 'social', 'governance', 'company_info', 'content', 'chart')
  ),
  CONSTRAINT chk_data_type CHECK (
    data_type IN ('quantitative', 'qualitative', 'narrative', 'binary')
  ),
  CONSTRAINT chk_unified_or_unmapped CHECK (
    (unified_column_id IS NOT NULL AND unmapped_dp_id IS NULL)
    OR (unified_column_id IS NULL AND unmapped_dp_id IS NOT NULL)
  )
);
```

**데이터 매핑 예시**:

**예시 1: GHG 배출량 (environmental_data → unified_column)**
```sql
-- environmental_data에서 데이터 가져오기
INSERT INTO sr_report_unified_data (
  company_id, period_year,
  source_entity_type, source_entity_id,
  unified_column_id, unmapped_dp_id,
  data_value, data_type, unit,
  data_source
)
SELECT 
  ed.company_id,
  ed.period_year,
  'environmental' AS source_entity_type,
  ed.id AS source_entity_id,
  '001_aa' AS unified_column_id,  -- "Scope 1 배출량" 통합 컬럼
  NULL AS unmapped_dp_id,         -- UCM 경로: 미매핑 FK는 NULL
  jsonb_build_object('value', ed.scope1_total_tco2e) AS data_value,
  'quantitative' AS data_type,
  'tCO2e' AS unit,
  'ghg_emission_results' AS data_source
FROM environmental_data ed
WHERE ed.company_id = 'company-001'
  AND ed.period_year = 2024
  AND ed.status = 'final_approved';
```

**예시 2: 임직원 수 (social_data → unified_column)**
```sql
INSERT INTO sr_report_unified_data (
  company_id, period_year,
  source_entity_type, source_entity_id,
  unified_column_id, unmapped_dp_id,
  data_value, data_type, unit,
  data_source
)
SELECT 
  sd.company_id,
  sd.period_year,
  'social' AS source_entity_type,
  sd.id AS source_entity_id,
  '002_ab' AS unified_column_id,  -- "총 임직원 수" 통합 컬럼
  NULL AS unmapped_dp_id,
  jsonb_build_object('value', sd.total_employees) AS data_value,
  'quantitative' AS data_type,
  '명' AS unit,
  'hr' AS data_source
FROM social_data sd
WHERE sd.company_id = 'company-001'
  AND sd.period_year = 2024
  AND sd.data_type = 'workforce'
  AND sd.status = 'final_approved';
```

**예시 3: SR 본문 (sr_report_content → unified_column)**
```sql
INSERT INTO sr_report_unified_data (
  company_id, period_year,
  source_entity_type, source_entity_id,
  unified_column_id, unmapped_dp_id,
  data_value, data_type,
  data_source
)
SELECT 
  src.company_id,
  EXTRACT(YEAR FROM src.created_at)::INTEGER AS period_year,
  'content' AS source_entity_type,
  src.id AS source_entity_id,
  '003_ac' AS unified_column_id,  -- "온실가스 배출량 설명" 통합 컬럼
  NULL AS unmapped_dp_id,
  jsonb_build_object('text', src.content_text) AS data_value,
  'narrative' AS data_type,
  'sr_report_content' AS data_source
FROM sr_report_content src
WHERE src.company_id = 'company-001'
  AND src.saved_to_final_report = TRUE;
```

**예시 4: 미매핑 DP (unmapped_data_points → 통합 행; `unified_column_id`는 NULL)**

```sql
-- 미매핑 DP 레코드가 준비된 뒤, 동일 회사·연도 사실을 적재
INSERT INTO sr_report_unified_data (
  company_id, period_year,
  source_entity_type, source_entity_id,
  unified_column_id, unmapped_dp_id,
  data_value, data_type, unit,
  data_source
)
VALUES (
  'company-001',
  2024,
  'environmental',
  (SELECT id FROM environmental_data WHERE company_id = 'company-001' AND period_year = 2024 LIMIT 1),
  NULL,                                           -- 미매핑 경로: UCM FK는 NULL
  'b8e3f0a2-....',                               -- unmapped_data_points.id (예시 UUID)
  '{"value": 100.0}'::jsonb,
  'quantitative',
  'tCO2e',
  'manual'
);
```

**UnifiedColumnMapping / 미매핑과의 연결 구조**:

**UCM 경로** 예:
```
unified_column_mappings 테이블:
- unified_column_id: '001_aa'
- column_name_ko: 'Scope 1 배출량'
- mapped_dp_ids: ['IFRS_S2-S2-29-a', 'GRI-305-1']
- column_category: 'E'
- column_type: 'quantitative'

sr_report_unified_data 테이블:
- unified_column_id: '001_aa' (FK)
- unmapped_dp_id: NULL
- data_value: {"value": 1234.5}
- source_entity_type: 'environmental'
- source_entity_id: (environmental_data.id)
```

**미매핑 경로** 예:
```
unmapped_data_points 테이블:
- id: (UUID)
- dp_id: 'NEW_STD-XX-01'
- standard_code: 'CUSTOM'

sr_report_unified_data 테이블:
- unified_column_id: NULL
- unmapped_dp_id: (위 unmapped_data_points.id, FK)
- data_value: {...}
```

**SR 보고서 생성 시 활용**:
```sql
-- (1) UCM 경로: 특정 기준서(IFRS S2)의 DP에 해당하는 데이터 조회
SELECT 
  ucm.unified_column_id,
  ucm.column_name_ko,
  ucm.column_name_en,
  ucm.mapped_dp_ids,
  srud.data_value,
  srud.data_type,
  srud.unit,
  srud.source_entity_type,
  srud.source_entity_id
FROM unified_column_mappings ucm
INNER JOIN sr_report_unified_data srud 
  ON ucm.unified_column_id = srud.unified_column_id
WHERE srud.company_id = 'company-001'
  AND srud.period_year = 2024
  AND srud.included_in_final_report = TRUE
  AND 'IFRS_S2-S2-29-a' = ANY(ucm.mapped_dp_ids)  -- IFRS S2 DP 필터링
ORDER BY ucm.unified_column_id;

-- (2) 미매핑 경로: 특정 dp_id로 사실 조회 (온톨로지 조인 없음)
SELECT 
  srud.id,
  udp.dp_id,
  udp.standard_code,
  udp.dp_name,
  srud.data_value,
  srud.data_type,
  srud.unit,
  srud.source_entity_type,
  srud.source_entity_id
FROM sr_report_unified_data srud
INNER JOIN unmapped_data_points udp ON udp.id = srud.unmapped_dp_id
WHERE srud.company_id = 'company-001'
  AND srud.period_year = 2024
  AND srud.included_in_final_report = TRUE
  AND udp.dp_id = 'NEW_STD-XX-01';

-- (3) 한 화면에서 병렬 조회: UCM 행과 미매핑 행을 UNION (컬럼 정렬은 앱/뷰에서 통일)
-- SELECT ... FROM (... UCM JOIN ...) u
-- UNION ALL
-- SELECT ... FROM (... unmapped JOIN ...) m;
```

**장점**:
- **통합 조회**: 6개 테이블을 하나의 뷰로 조회 가능
- **기준서 매핑**: UnifiedColumnMapping을 통해 다중 기준서 지원
- **유연성**: JSONB로 다양한 데이터 타입 저장
- **추적성**: 원본 테이블 참조 유지 (`source_entity_type`, `source_entity_id`)
- **확장성**: 새로운 소스 테이블 추가 용이
- **미매핑 DP**: 온톨로지 편입 전에도 동일 테이블에 사실 적재 가능(`unmapped_data_points`)

**고려사항**:
- **데이터 동기화**: 소스 테이블 변경 시 통합 테이블 업데이트 필요 (트리거 또는 배치 작업)
- **중복 데이터**: 같은 `unified_column_id`에 여러 소스가 있을 수 있음 → 우선순위 로직 필요 (예: `final_approved` > `approved` > `draft`)
- **UCM ↔ 미매핑 전환**: DP가 `unified_column_mappings`에 추가되면 해당 사실 행을 **미매핑에서 UCM으로 이전**하는 마이그레이션(같은 행에서 `unmapped_dp_id` NULL 처리 + `unified_column_id` 설정, 또는 행 분리) 정책이 필요
- **성능**: 대량 데이터 시 인덱스 최적화 필요

---

### 2.8 전년도 SR 보고서 파싱 테이블

전년도 SR 보고서 PDF를 파싱하여 Index(DP→페이지 매핑), 본문, 이미지를 저장합니다. RAG·벤치마킹에서 참조합니다. 상세 파서 설계는 [HISTORICAL_REPORT_PARSING.md](./HISTORICAL_REPORT_PARSING.md)를 참조하세요.

**스키마 참고**: `historical_sr_reports.pdf_file_path`, `sr_report_images.image_file_path` 컬럼은 Alembic `016_drop_sr_paths`에서 제거되었습니다. `sr_report_index`, `sr_report_body`는 원래 로컬 `file_path` 컬럼이 없습니다.

#### `historical_sr_reports` - 보고서 메타데이터

**역할**: 회사·연도별 전년도 SR 보고서 1건 메타데이터

```sql
CREATE TABLE historical_sr_reports (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL,
    report_year INTEGER NOT NULL,
    report_name TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'dart' | 'manual_upload'
    total_pages INTEGER,
    index_page_numbers INTEGER[],  -- Index 페이지 번호들 [146, 147]
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(company_id, report_year),
    INDEX idx_historical_company_year (company_id, report_year)
);
```

#### `sr_report_index` - Index 테이블 (DP → 페이지 매핑)

**역할**: 기준서별 Index에서 Data Point ID별로 해당 페이지 번호 배열 저장

```sql
CREATE TABLE sr_report_index (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES historical_sr_reports(id) ON DELETE CASCADE,
    
    index_type TEXT NOT NULL,  -- 'gri' | 'sasb' | 'ifrs' | 'esrs'
    index_page_number INTEGER,
    dp_id TEXT NOT NULL,  -- 'GRI-305-1', 'S2-15-a' 등
    dp_name TEXT,
    page_numbers INTEGER[] NOT NULL,  -- [131] 또는 [7, 8]
    section_title TEXT,
    remarks TEXT,
    
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsing_method TEXT DEFAULT 'docling',
    confidence_score DECIMAL(5, 2),
    
    INDEX idx_index_report (report_id),
    INDEX idx_index_dp (dp_id),
    INDEX idx_index_pages (page_numbers) USING GIN
);
```

#### `sr_report_body` - 본문 테이블 (페이지별 본문)

**역할**: 보고서 페이지별 본문 텍스트, 문단 분할, 임베딩 상태, **인쇄 목차(Contents) 상의 위치**

**`toc_path` vs `sr_report_index`**:  
- **`sr_report_index`**: GRI·IFRS S2·SASB 등 **공시 프레임워크 인덱스**(dp_id, 지표명, 페이지 매핑).  
- **`toc_path`**: PDF 앞부분 **보고서 자체 목차**(예: INTRODUCTION → CEO 인사말, ESG PERFORMANCE → ENVIRONMENTAL → 기후변화 대응)를 문자열 배열로 담는다.  
  목차 항목은 보통 **시작 페이지**만 제시되므로, 파이프라인에서는 “시작 페이지 ≤ 현재 페이지”인 **가장 최근 목차 항목**으로 구간을 할당해 채운다(초기에는 `NULL` 허용).

```sql
CREATE TABLE sr_report_body (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES historical_sr_reports(id) ON DELETE CASCADE,
    
    page_number INTEGER NOT NULL,
    is_index_page BOOLEAN DEFAULT FALSE,
    content_text TEXT NOT NULL,
    content_type TEXT,  -- 'narrative' | 'quantitative' | 'table' | 'mixed'
    paragraphs JSONB,
    toc_path JSONB,  -- 예: ["ESG PERFORMANCE","ENVIRONMENTAL","기후변화 대응"] — 인쇄 목차 계층(루트→리프)
    embedding_id TEXT,
    embedding_status TEXT DEFAULT 'pending',
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(report_id, page_number),
    INDEX idx_body_report_page (report_id, page_number),
    INDEX idx_body_embedding (embedding_status),
    INDEX idx_body_toc_path ON sr_report_body USING GIN (toc_path)
);
```

#### `sr_report_images` - 이미지 테이블

**역할**: 보고서 내 이미지(차트·그래프·사진 등) 메타(크기·캡션·추출 데이터), 임베딩 상태. 로컬 파일 경로는 저장하지 않습니다. 선택적으로 원본 래스터를 DB에 둘 수 있습니다(`image_blob`, Alembic `017_sr_images_blob`). 바이트 크기 전용 컬럼 `image_file_size`는 Alembic `018_drop_sr_image_file_size`에서 제거되었으며, 필요 시 `extracted_data.size_bytes` 또는 `image_blob` 길이로 표현합니다.

```sql
CREATE TABLE sr_report_images (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES historical_sr_reports(id) ON DELETE CASCADE,
    
    page_number INTEGER NOT NULL,
    image_index INTEGER,
    image_blob BYTEA,  -- 선택: 인메모리/SR_IMAGE_PERSIST_BLOB 등으로 저장 시
    image_width INTEGER,
    image_height INTEGER,
    image_type TEXT,  -- 'chart' | 'graph' | 'photo' | 'diagram' | 'table' | 'unknown'
    caption_text TEXT,
    caption_confidence DECIMAL(5, 2),
    extracted_data JSONB,
    caption_embedding_id TEXT,
    embedding_status TEXT DEFAULT 'pending',
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    INDEX idx_images_report_page (report_id, page_number),
    INDEX idx_images_type (image_type),
    INDEX idx_images_embedding (embedding_status)
);
```

---

### 2.9 벤치마킹·평가 테이블

뉴스·외부 피드백 기반 SR 보고서 평가 및 벤치마킹에 사용합니다. 상세 플로우는 [SR_REPORT_BENCHMARKING.md](./SR_REPORT_BENCHMARKING.md)를 참조하세요.

#### `news_articles` - 뉴스 기사

**역할**: ESG 관련 뉴스 크롤링 결과, 관련성·감정·핵심 이슈 저장

```sql
CREATE TABLE news_articles (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL,
    
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'naver', 'daum', 'google' 등
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    
    esg_relevance_score DECIMAL(5, 2),
    esg_topics TEXT[],
    related_dp_ids TEXT[],
    sentiment TEXT,  -- 'positive' | 'negative' | 'neutral'
    sentiment_score DECIMAL(5, 2),
    key_issues JSONB,
    
    crawled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    INDEX idx_news_company_date (company_id, published_at),
    INDEX idx_news_relevance (esg_relevance_score),
    INDEX idx_news_sentiment (sentiment)
);
```

#### `sr_report_evaluations` - SR 보고서 평가

**역할**: 회사·보고연도별 종합 평가 점수, 뉴스/공시/외부평가 피드백, 개선점

```sql
CREATE TABLE sr_report_evaluations (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL,
    report_year INTEGER NOT NULL,
    evaluation_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    overall_score DECIMAL(5, 2) NOT NULL,
    news_sentiment_score DECIMAL(5, 2),
    news_sentiment_impact DECIMAL(5, 2),
    disclosure_alignment_score DECIMAL(5, 2),
    issue_coverage_score DECIMAL(5, 2),
    external_rating_score DECIMAL(5, 2),
    ifrs_compliance_score DECIMAL(5, 2),
    completeness_score DECIMAL(5, 2),
    credibility_score DECIMAL(5, 2),
    
    news_feedback_summary JSONB,
    disclosure_feedback_summary JSONB,
    external_rating_feedback JSONB,
    improvement_areas JSONB,
    evaluation_rationale TEXT,
    evaluated_by TEXT DEFAULT 'system',
    
    INDEX idx_eval_company_year (company_id, report_year),
    INDEX idx_eval_score (overall_score),
    INDEX idx_eval_date (evaluation_date)
);
```

---

## 3. 테이블 간 관계 및 데이터 흐름

### 3.1 GHG 산정 데이터 흐름

```
[EMS/ERP/EHS] 원시 데이터
    ↓
[ghg_activity_data] 활동자료 저장
    ↓
[배출계수 조회] ghg_emission_factors 조회
    ↓
[ghg_calculation_evidence] 산정 근거 저장 (스냅샷)
    - applied_factor_id, applied_factor_value
    - calculation_formula, ghg_emission_tco2e
    - 재산정 이력 추적 (previous_evidence_id)
    ↓
[ghg_emission_results] 배출량 산정 결과 저장 (집계)
    ↓
[사용자] "저장" 버튼 클릭
    ↓
[ghg_calculation_snapshots] 버전 저장 (v1, v2, v3...)
    - emission_result_id: FK 참조 (원본 추적)
    - payload: JSONB로 데이터 복사 (시점 고정)
    - is_locked: FALSE
    ↓
[사용자] "마감" 버튼 클릭 (선택)
    ↓
[ghg_calculation_snapshots] 마감 상태 업데이트
    - is_locked: TRUE
    - locked_by, locked_at, lock_reason 저장
    ↓
[environmental_data] SR 보고서용 환경 데이터 집계 (마감된 버전 사용)
```

**산정 근거 테이블의 역할**:
- 각 활동자료 행별로 산정 근거 정보 저장
- 배출계수 스냅샷 보존 (MDG 배출계수 변경 시에도 당시 값 유지)
- 재산정 이력 추적 (같은 활동자료로 여러 번 산정해도 이력 보존)
- 감사 추적 및 산정 근거 화면 표시에 활용

### 3.2 SR 보고서 자동 작성 데이터 흐름

**기존 방식 (개별 테이블 직접 조회)**:
```
[데이터 소스]                    [테이블]                      [SR 보고서 생성]
─────────────────              ────────────              ─────────────────
GHG 산정 결과            →    ghg_emission_results  →    "온실가스 배출량" 문단
                                                          Scope 1/2/3 수치 삽입

환경 데이터 (에너지/용수)  →    environmental_data    →    "에너지 사용량" 문단
                                                          "용수 관리" 문단

사회 데이터 (임직원/안전)   →    social_data          →    "인력 구성" 문단
                                                          "안전보건" 문단

지배구조 데이터           →    governance_data       →    "이사회" 문단
                                                          "컴플라이언스" 문단

회사정보                 →    company_info          →    표지, 회사 소개

SR 작성 문단             →    sr_report_content     →    본문 텍스트

차트/도표                →    esg_charts            →    차트 이미지 삽입
```

**개선된 방식 (통합 테이블 + UnifiedColumnMapping)**:
```
[데이터 소스]                    [소스 테이블]              [통합 테이블]              [매핑]              [SR 보고서 생성]
─────────────────              ────────────              ────────────              ───────              ─────────────────
GHG 산정 결과            →    ghg_emission_results  →    sr_report_unified_data  →  unified_column_  →  "온실가스 배출량" 문단
환경 데이터 (에너지/용수)  →    environmental_data    →    (통합 저장)          →  mappings         →  "에너지 사용량" 문단
사회 데이터 (임직원/안전)   →    social_data          →    - source_entity_type   →  (기준서별 DP)    →  "인력 구성" 문단
지배구조 데이터           →    governance_data       →    - source_entity_id     →                   →  "이사회" 문단
회사정보                 →    company_info          →    - unified_column_id     →                   →  표지, 회사 소개
SR 작성 문단             →    sr_report_content     →    - data_value (JSONB)   →                   →  본문 텍스트
차트/도표                →    esg_charts            →    - data_type            →                   →  차트 이미지 삽입
미매핑 DP(온톨로지 전)   →    (위 6종 소스 중 해당)  →    - unmapped_dp_id SET  →  unmapped_data_   →  해당 공시·문단
                                                          (unified_column_id NULL) →  points
```

**통합 테이블의 역할**:
1. **데이터 통합**: 6개 소스 테이블의 데이터를 하나의 테이블로 통합
2. **의미 축 매핑**: (a) `unified_column_mappings` — IFRS S2, GRI, TCFD 등 다중 기준서 Data Point; (b) `unmapped_data_points` — 아직 통합 컬럼이 없는 DP. 한 행은 **UCM(`unified_column_id`)과 미매핑 FK(`unmapped_dp_id`) 중 정확히 하나만** 설정한다(`chk_unified_or_unmapped`).
3. **효율적 조회**: 기준서별로 필요한 데이터를 한 번의 조회로 가져올 수 있음(UCM 경로는 `mapped_dp_ids` 조인, 미매핑 경로는 `unmapped_data_points` 조인)
4. **원본 추적**: `source_entity_type`과 `source_entity_id`로 원본 테이블 참조 유지

### 3.3 데이터 집계 로직

#### `environmental_data` 자동 집계 예시

```sql
-- 에너지 사용량 집계 (ghg_activity_data에서)
INSERT INTO environmental_data (
  company_id,
  period_year,
  total_energy_consumption_mwh,
  renewable_energy_mwh,
  total_waste_generated,
  waste_recycled,
  ghg_data_source
)
SELECT 
  company_id,
  period_year,
  -- 총 에너지 소비량 집계
  SUM(CASE 
    WHEN tab_type = 'power_heat_steam' 
    THEN usage_amount * 
      CASE usage_unit
        WHEN 'kWh' THEN 1.0 / 1000.0
        WHEN 'Gcal' THEN 1.163 / 1000.0
        WHEN 'GJ' THEN 0.2778 / 1000.0
        ELSE 0
      END
    WHEN tab_type = 'fuel_vehicle'
    THEN usage_amount * fuel_to_mwh_factor
    ELSE 0
  END) as total_energy_consumption_mwh,
  
  -- 재생에너지 집계
  SUM(CASE 
    WHEN tab_type = 'power_heat_steam' 
    THEN usage_amount * renewable_ratio / 100.0
    ELSE 0
  END) as renewable_energy_mwh,
  
  -- 폐기물 집계
  SUM(CASE 
    WHEN tab_type = 'waste' 
    THEN generation_amount 
    ELSE 0 
  END) as total_waste_generated,
  
  SUM(CASE 
    WHEN tab_type = 'waste' 
    THEN recycling_amount 
    ELSE 0 
  END) as waste_recycled,
  
  'ghg_activity_data' as ghg_data_source
  
FROM ghg_activity_data
WHERE company_id = ?
  AND period_year = ?
GROUP BY company_id, period_year;
```

### 3.4 데이터베이스 관계 방식 정리

플랫폼에서 사용하는 테이블 간 관계를 **관계 유형**별로 정리한다. 설계·조회·JOIN 시 참고용이다.

#### 1) 일반 FK (1:1 / 1:N)

한 테이블의 PK를 다른 테이블의 컬럼이 직접 참조하는 방식. 대부분의 “단일 부모” 관계에 사용한다.

| 자식 테이블 | FK 컬럼 | 부모 테이블(PK) | 비고 |
|-------------|---------|------------------|------|
| ghg_calculation_snapshots | emission_result_id | ghg_emission_results(id) | 원본 추적 |
| ghg_unlock_requests | period_lock_id | ghg_period_locks(id) | |
| ghg_approval_steps | workflow_id | ghg_approval_workflows(id) | |
| workflow_approval_steps | workflow_id | workflow_approvals(id) | ON DELETE CASCADE |
| sr_report_index | report_id | historical_sr_reports(id) | ON DELETE CASCADE |
| sr_report_body | report_id | historical_sr_reports(id) | ON DELETE CASCADE |
| sr_report_images | report_id | historical_sr_reports(id) | ON DELETE CASCADE |
| sr_report_unified_data | company_id | companies(id) | |
| sr_report_unified_data | unified_column_id | unified_column_mappings(unified_column_id) | NULL 허용; 미매핑 행에서는 NULL. `chk_unified_or_unmapped`로 두 FK 상호 배타 |
| sr_report_unified_data | unmapped_dp_id | unmapped_data_points(id) | NULL 허용; UCM 행에서는 NULL. 위와 동일 CHK |
| page_progress | company_id, assignee_id, completed_by | companies(id), users(id) | |
| notifications | company_id, user_id, template_id | companies(id), users(id), notification_templates(id) | |
| notification_reads | notification_id, user_id | notifications(id), users(id) | ON DELETE CASCADE |
| ghg_audit_logs | company_id, changed_by | companies(id), users(id) | changed_by: ON DELETE RESTRICT |

#### 2) Polymorphic Association (다형 참조)

한 (type, id) 쌍이 **타입 값에 따라 서로 다른 테이블**의 PK를 가리키는 방식. DB 레벨 FK 제약은 걸 수 없고, 조회 시 타입별로 JOIN한다.

| 테이블 | 타입 컬럼 | ID 컬럼 | 참조 후보 테이블 | 용도 |
|--------|-----------|---------|------------------|------|
| **sr_report_unified_data** | source_entity_type | source_entity_id | environmental_data, social_data, governance_data, company_info, sr_report_content, esg_charts | “이 행의 값이 어느 소스 테이블의 어떤 행에서 왔는지” |
| **ghg_audit_logs** | entity_type | entity_id | ghg_activity_data, ghg_emission_results, ghg_calculation_snapshots | 변경 대상 엔티티 지정 |
| **notifications** | related_entity_type | related_entity_id | review_request, todo, page_progress, report_export, workflow_approval 등 | 알림이 가리키는 엔티티 |
| **workflow_approvals** | related_entity_type | related_entity_id | ghg_calculation_snapshots, review_request 등 | 승인 대상 엔티티 |
| **ghg_evidence_files** | related_entity_type | related_entity_id | ghg_activity_data, ghg_emission_results | 증빙이 연결된 엔티티 |
| **ghg_audit_comments** | related_entity_type | related_entity_id | (다양) | 코멘트가 연결된 엔티티 |

**JOIN 예시 (sr_report_unified_data)**  
`source_entity_type` 값에 따라 `source_entity_id`를 해당 테이블의 PK와 매칭한다.

```sql
LEFT JOIN environmental_data ed ON ed.id = srud.source_entity_id AND srud.source_entity_type = 'environmental'
LEFT JOIN social_data sd ON sd.id = srud.source_entity_id AND srud.source_entity_type = 'social'
LEFT JOIN governance_data gd ON gd.id = srud.source_entity_id AND srud.source_entity_type = 'governance'
```

#### 3) 논리적 참조 (FK 미적용)

다른 테이블의 PK/식별자를 **의미적으로만** 참조하고, DB에는 FOREIGN KEY를 두지 않는 경우.

| 테이블 | 컬럼 | 논리적 참조 대상 | 비고 |
|--------|------|------------------|------|
| **rulebooks** | standard_id | standards(standard_id, section_name) 복합 PK | standards가 복합 PK라 FK 미적용 |
| **rulebooks** | primary_dp_id | data_points(dp_id) | |
| **unified_column_mappings** | mapped_dp_ids | data_points.dp_id 여러 개 (ARRAY) | 배열이라 FK 불가 |

#### 4) 1:N + 스냅샷/복사 (FK + JSONB 복사)

원본을 FK로 가리키되, **시점 고정**을 위해 값은 JSONB 등으로 복사해 두는 패턴.

| 테이블 | FK | 복사 저장 | 용도 |
|--------|-----|-----------|------|
| **ghg_calculation_snapshots** | emission_result_id → ghg_emission_results(id) | payload (JSONB) | “어느 결과를 스냅샷했는지” 추적 + 마감 시점 데이터 고정 |

#### 5) UNIQUE로 강제하는 1:1 (또는 “키당 1건”)

한 (회사, 타입 등) 조합당 **행이 하나만** 있도록 UNIQUE로 제한하는 방식.

| 테이블 | UNIQUE 제약 | 의미 |
|--------|-------------|------|
| historical_sr_reports | (company_id, report_year) | 회사·연도당 보고서 1건 |
| sr_report_body | (report_id, page_number) | 보고서·페이지당 본문 1건 |
| page_progress | (company_id, page_type) | 회사·페이지타입당 진행 1건 |
| progress_snapshots | (company_id, snapshot_date) | 회사·날짜당 스냅샷 1건 |
| user_notification_settings | (user_id, notification_type) | 사용자·알림타입당 설정 1건 |

#### 6) 배열(ARRAY)로 “N쪽” 표현 (FK 아님)

한 행이 **여러 개의 식별자**를 배열로 갖는 방식. DB FK로는 표현하지 않고, 앱/조회에서만 해석한다.

| 테이블 | 배열 컬럼 | 의미 |
|--------|-----------|------|
| unified_column_mappings | mapped_dp_ids (TEXT[]) | 이 통합 컬럼에 매핑된 여러 DP ID |
| historical_sr_reports | index_page_numbers (INTEGER[]) | Index 페이지 번호 목록 |
| sr_report_index | page_numbers (INTEGER[]) | 해당 DP가 나오는 페이지 번호들 |

#### 7) 온톨로지/기준서 쪽 계층 (DATA_ONTOLOGY)

기준서·룰북·통합컬럼·공시방법 간 관계. 물리적으로는 FK + 논리적 참조 혼합.

| 관계 | 방식 | 비고 |
|------|------|------|
| standards ← rulebooks | 논리적 참조 (standard_id) | standards 복합 PK라 FK 없음 |
| data_points ← rulebooks | primary_dp_id (논리적) | |
| rulebooks ← unified_column_mappings | primary_rulebook_id (FK 가능) | 문서 다이어그램 기준 |
| unified_column_mappings ← disclosure_methods | unified_column_id (FK) | 1:N |

#### 8) CASCADE / RESTRICT 정책

| 테이블/컬럼 | 정책 | 의도 |
|-------------|------|------|
| ghg_audit_logs.changed_by → users(id) | ON DELETE RESTRICT | 사용자 삭제 시 감사 로그 보존 |
| notification_reads.notification_id | ON DELETE CASCADE | 알림 삭제 시 읽음 기록도 삭제 |
| workflow_approval_steps.workflow_id | ON DELETE CASCADE | 워크플로 삭제 시 단계도 삭제 |
| historical_sr_reports 삭제 시 | sr_report_* ON DELETE CASCADE | 보고서 삭제 시 index/body/images 함께 삭제 |

#### 9) 관계 방식 요약

| 관계 방식 | 플랫폼 사용처 | 판단 |
|-----------|----------------|------|
| **일반 FK (1:N, 1:1)** | 회사/사용자/보고서/워크플로/통합컬럼/알림 등 | **필수** |
| **Polymorphic Association** | sr_report_unified_data 소스, 감사/알림/승인/증빙/코멘트의 “대상 엔티티” | **필수** |
| **논리적 참조 (FK 없음)** | rulebooks → standards, rulebooks → data_points, mapped_dp_ids | **필수** (복합 PK·배열 등 제약) |
| **FK + JSONB 스냅샷** | ghg_calculation_snapshots | **필수** (마감/버전 이력) |
| **UNIQUE로 1:1(또는 키당 1건)** | historical_sr_reports, page_progress, progress_snapshots 등 | **필수** |
| **ARRAY로 N 표현** | mapped_dp_ids, page_numbers, index_page_numbers | **선택·권장** |
| **상호 배타 이중 FK (UCM / 미매핑)** | `sr_report_unified_data.unified_column_id` vs `unmapped_dp_id` + `chk_unified_or_unmapped` | **필수** (2.7 스키마) |

---

## 4. 데이터 확정 프로세스

### 4.1 GHG 산정 데이터 확정

```
[사용자] GHG 산정 결과 저장
  ↓
[시스템] ghg_emission_results 저장 (집계된 배출량)
  ↓
[사용자] "이 탭 결과 저장" 또는 "전체 결과 저장" 클릭
  ↓
[시스템] ghg_calculation_snapshots 생성 (v1, v2, v3...)
  - emission_result_id: 현재 ghg_emission_results.id를 FK로 참조
  - payload: 현재 ghg_emission_results의 모든 데이터를 JSONB로 복사 저장
  - snapshot_version: 다음 버전 번호 자동 생성 (v1 → v2 → v3...)
  - is_locked: FALSE (아직 마감 안됨)
  ↓
[사용자] "마감" 버튼 클릭 (선택)
  ↓
[시스템] ghg_calculation_snapshots 업데이트
  - is_locked: TRUE
  - locked_by: 사용자 ID
  - locked_at: 현재 시각
  - lock_reason: 마감 사유
  ↓
[확정] SR 보고서 생성 시 마감된 버전(is_locked = TRUE) 사용
```

**중요 사항**:
- **FK 참조**: `emission_result_id`는 원본 추적용으로만 사용
- **데이터 복사**: `payload`에 스냅샷 시점의 데이터를 복사 저장하여 원본이 이후 변경되어도 스냅샷 값 유지
- **버전 관리**: 같은 기간에 여러 버전 저장 가능 (v1, v2, v3...)
- **마감 관리**: `is_locked = TRUE`인 버전이 최종 확정 버전

**사용 예시**:

```sql
-- 저장 버튼 클릭 시: FK 참조 + 데이터 복사
INSERT INTO ghg_calculation_snapshots (
  company_id, period_year, period_month,
  snapshot_version, emission_result_id,  -- FK 참조
  payload,  -- 데이터 복사
  is_locked, created_by
)
SELECT 
  company_id, period_year, period_month,
  'v2',  -- 다음 버전 (자동 계산)
  id,  -- FK 참조
  jsonb_build_object(  -- 데이터 복사
    'scope1_total_tco2e', scope1_total_tco2e,
    'scope1_fixed_combustion_tco2e', scope1_fixed_combustion_tco2e,
    'scope1_mobile_combustion_tco2e', scope1_mobile_combustion_tco2e,
    'scope1_fugitive_tco2e', scope1_fugitive_tco2e,
    'scope1_incineration_tco2e', scope1_incineration_tco2e,
    'scope2_location_tco2e', scope2_location_tco2e,
    'scope2_market_tco2e', scope2_market_tco2e,
    'scope2_renewable_tco2e', scope2_renewable_tco2e,
    'scope3_total_tco2e', scope3_total_tco2e,
    'scope3_category_1_tco2e', scope3_category_1_tco2e,
    'scope3_category_4_tco2e', scope3_category_4_tco2e,
    'scope3_category_6_tco2e', scope3_category_6_tco2e,
    'scope3_category_7_tco2e', scope3_category_7_tco2e,
    'scope3_category_9_tco2e', scope3_category_9_tco2e,
    'scope3_category_11_tco2e', scope3_category_11_tco2e,
    'scope3_category_12_tco2e', scope3_category_12_tco2e,
    'total_tco2e', total_tco2e,
    'applied_framework', applied_framework,
    'calculation_version', calculation_version,
    'data_quality_score', data_quality_score,
    'data_quality_level', data_quality_level
  ),
  FALSE,  -- 아직 마감 안됨
  'user_001'
FROM ghg_emission_results
WHERE company_id = 'company-001' 
  AND period_year = 2024 
  AND period_month = 1;

-- 마감 버튼 클릭 시
UPDATE ghg_calculation_snapshots
SET 
  is_locked = TRUE,
  locked_by = 'user_001',
  locked_at = NOW(),
  lock_reason = '2024년 1월 최종 마감',
  updated_at = NOW()
WHERE company_id = 'company-001'
  AND period_year = 2024
  AND period_month = 1
  AND snapshot_version = 'v2';

-- 마감된 최신 버전 조회
SELECT 
  snapshot_version,
  label,
  payload->>'scope1_total_tco2e' as scope1,  -- 스냅샷 시점 값
  payload->>'scope2_location_tco2e' as scope2,
  payload->>'total_tco2e' as total,
  is_locked,
  locked_at,
  emission_result_id  -- 원본 참조
FROM ghg_calculation_snapshots
WHERE company_id = 'company-001'
  AND period_year = 2024
  AND period_month = 1
  AND is_locked = TRUE
ORDER BY snapshot_version DESC
LIMIT 1;

-- 모든 버전 조회 (마감 여부 포함)
SELECT 
  snapshot_version,
  label,
  is_locked,
  locked_at,
  payload->>'total_tco2e' as total_emission,
  created_at
FROM ghg_calculation_snapshots
WHERE company_id = 'company-001'
  AND period_year = 2024
ORDER BY created_at DESC;

-- 마감 해제
UPDATE ghg_calculation_snapshots
SET 
  is_locked = FALSE,
  unlocked_by = 'user_001',
  unlocked_at = NOW(),
  unlock_reason = '데이터 오류 정정 필요',
  updated_at = NOW()
WHERE id = 'snapshot-uuid';
```

### 4.2 ESG 데이터 확정 (승인 워크플로우)

```
[현업팀] environmental_data / social_data / governance_data 입력
  ↓
[현업팀] "검토 요청" 버튼 클릭
  ↓
[시스템] status = 'pending_review'
  ↓
[ESG팀] 데이터 검토 후 "승인" 또는 "반려" 클릭
  ↓
[시스템] status = 'approved' 또는 'rejected'
  ↓
[ESG팀] "최종 승인 요청" 클릭
  ↓
[최종 승인권자] 최종 승인 클릭
  ↓
[시스템] status = 'final_approved'
  ↓
[확정] SR 보고서 생성 시 이 데이터 사용
```

### 4.3 회사정보 확정

```
[사용자] 회사정보 페이지에서 데이터 입력
  ↓
[사용자] "최종 보고서에 제출" 버튼 클릭
  ↓
[시스템] company_info.submitted_to_final_report = TRUE
  ↓
[확정] SR 보고서 생성 시 이 데이터 사용
```

### 4.4 SR 본문 및 차트 확정

```
[사용자] SR 작성 페이지에서 문단 작성
  ↓
[사용자] "저장" 또는 "최종보고서에 저장" 클릭
  ↓
[시스템] sr_report_content.saved_to_final_report = TRUE
  ↓
[확정] SR 보고서 생성 시 이 문단 사용

[사용자] 도표 및 그림 생성 페이지에서 차트 생성
  ↓
[사용자] "저장" 버튼 클릭
  ↓
[시스템] esg_charts.saved_to_final_report = TRUE
  ↓
[확정] SR 보고서 생성 시 이 차트 사용
```

---

## 5. 요약

### 5.1 GHG 산정 탭 테이블 (13개)

1. **핵심 데이터**: `ghg_activity_data`, `ghg_emission_results`, `ghg_emission_factors`, `ghg_calculation_evidence`
2. **감사 및 버전 관리**: `ghg_calculation_snapshots`, `ghg_audit_logs`
   - `ghg_calculation_snapshots`: 버전별 스냅샷 저장 및 마감 상태 관리 (FK 참조 + 데이터 복사 방식)
   - `ghg_audit_logs`: `activity_data`, `emission_results`, `calculation_snapshots` 세 테이블의 변경 이력 추적
     - `changed_by`: `users.id` (UUID) FK 참조
     - `company_id`: `companies.id` FK 참조
     - `entity_type`: 'activity_data' | 'emission_results' | 'calculation_snapshots'
3. **승인 및 잠금**: `ghg_period_locks`, `ghg_unlock_requests`, `ghg_approval_workflows`, `ghg_approval_steps`
   - `ghg_period_locks`: 마감 기능은 `ghg_calculation_snapshots`에 통합 (호환성 유지용)
   - `ghg_unlock_requests`: ⚠️ 레거시 테이블, `workflow_approvals`로 통합 예정 (`workflow_type = 'ghg_unlock'`)
   - `ghg_approval_workflows`, `ghg_approval_steps`: ⚠️ 레거시 테이블, `workflow_approvals`, `workflow_approval_steps`로 통합 예정
4. **증빙 및 공시**: `ghg_evidence_files`, `ghg_audit_comments`, `ghg_disclosure_requirements`

### 5.2 SR 보고서 자동 작성 테이블 (14개)

1. **통합 컬럼 매핑(온톨로지)**: `unified_column_mappings` (다중 기준서 DP ↔ 통합 컬럼 매핑, 벡터 임베딩)
2. **환경 데이터**: `environmental_data` (GHG 데이터는 `ghg_emission_results`에서, 에너지/폐기물은 `ghg_activity_data`에서 집계)
3. **사회 데이터**: `social_data` (HR, SRM 시스템에서 수집)
4. **지배구조 데이터**: `governance_data` (별도 시스템에서 수집)
5. **회사정보**: `company_info` (수동 입력)
6. **SR 본문**: `sr_report_content` (사용자 작성 또는 AI 생성)
7. **차트/도표**: `esg_charts` (사용자 생성)
8. **통합 데이터**: `sr_report_unified_data` (6개 소스 테이블 통합 + **UCM 또는** `unmapped_data_points`와 매핑)
   - 소스 테이블: `environmental_data`, `social_data`, `governance_data`, `company_info`, `sr_report_content`, `esg_charts`
   - **UCM 행**: `unified_column_mappings`를 통해 IFRS S2, GRI, TCFD 등 다중 기준서의 Data Point와 연결
   - **미매핑 행**: `unmapped_data_points` FK만 설정(`unified_column_id`는 NULL); 이후 온톨로지 편입 시 전환 정책 적용
   - 기준서별 SR 보고서 생성 시 효율적인 데이터 조회 지원
9. **전년도 SR 파싱**: `historical_sr_reports`, `sr_report_index`, `sr_report_body`, `sr_report_images` (PDF 파싱·RAG·벤치마킹 참조)
10. **벤치마킹·평가**: `news_articles` (ESG 뉴스 수집·분석), `sr_report_evaluations` (보고서 종합 평가)

### 5.3 데이터 확정 조건

- **GHG 산정**: 
  - 버전 저장: "저장" 버튼 클릭 시 `ghg_calculation_snapshots`에 버전 저장 (FK 참조 + 데이터 복사)
  - 마감 확정: "마감" 버튼 클릭 시 `is_locked = TRUE`로 설정하여 최종 확정
- **ESG 데이터**: 승인 워크플로우 완료 시 확정 (`status = 'final_approved'`)
- **회사정보**: "최종 보고서에 제출" 클릭 시 확정
- **SR 본문/차트**: "저장" 또는 "최종보고서에 저장" 클릭 시 확정
- **SR 통합 데이터**: 
  - 소스 테이블의 `status = 'final_approved'` 또는 `saved_to_final_report = TRUE`인 데이터만 통합 테이블에 반영
  - "최종보고서에 포함" 클릭 시 `included_in_final_report = TRUE`로 설정하여 SR 보고서 생성 시 사용

### 5.4 대시보드 및 시스템 관리 테이블 (13개)

1. **진행률 집계**: `page_progress`, `progress_snapshots`
2. **알림 관리**: `notifications`, `notification_templates`, `notification_preferences`, `notification_delivery_logs`
3. **할 일 리스트**: `todos`
4. **팀원 현황 관리**: `team_assignments`, `team_activity_logs`
5. **리포트 출력**: `report_exports`
6. **코멘트 및 질의응답**: `comments` (범용 코멘트 테이블)
   - 감사 코멘트, 검토 요청, 피드백 통합 관리
   - 스레드 형태 질의응답 지원
   - ⚠️ 기존 `ghg_audit_comments`, `review_requests`는 레거시로 표시, `comments`로 통합 예정
7. **리마인드 스케줄링**: `reminder_schedules`
8. **승인 워크플로우**: `workflow_approvals`, `workflow_approval_steps`

### 5.5 온프레미스 로그인 및 사용자 관리 테이블 (4개)

1. **사용자 정보**: `users` (온프레미스용 - 초기 비밀번호, 최초 로그인 관리 포함)
2. **회사 정보**: `companies` (마감일, 최종 승인 정보 포함)
3. **세션 관리**: `user_sessions` (JWT 토큰, 세션 추적)
4. **비밀번호 재설정**: `password_reset_tokens` (비밀번호 재설정 토큰)

---

## 6. 향후 개선 사항: 데이터 수집 아키텍처

### 6.1 현재 설계의 위치

현재 `ghg_activity_data` 테이블은 **최종 사용 테이블(Target Table)**로 설계되었습니다. 이는 정제되고 변환된 데이터를 저장하는 단계입니다.

**현재 구조의 특징**:
- Single Table Inheritance 패턴 사용
- `tab_type`에 따라 해당 탭의 필드만 값이 있고 나머지는 NULL
- 한 행(row)은 하나의 `tab_type`만 가짐
- 통합 조회 및 집계에 유리

### 6.2 실제 기업 환경에서 사용하는 데이터 수집 방식

ERP/EMS/EHS 같은 외부 시스템에서 데이터를 받아올 때는 일반적으로 **ETL(Extract, Transform, Load) 프로세스**를 사용합니다.

#### 일반적인 ETL 프로세스

```
[EMS / ERP / EHS / PLM / SRM / HR / MDG]
    ↓ (API/File)
[Staging Tables] ← 시스템별 원본 데이터 전체 저장 (7개 테이블)
    ↓ (Transform)
[Validated Tables] ← 검증된 데이터
    ↓ (Load)
[Target Tables] ← 최종 사용 테이블 (ghg_activity_data)
```

### 6.3 권장 개선 구조

#### 옵션 1: 스테이징 테이블 패턴 (권장)

원본 데이터를 **시스템별로 7개 스테이징 테이블**에 나누어 저장합니다. 각 테이블은 해당 시스템에서 수집한 원본 데이터 전체를 보존합니다.

```sql
-- 레이어 1: 원본 데이터 (Staging) — 시스템별 7개 테이블
-- EMS: 전력·열·스팀, 에너지, 폐기물 등
CREATE TABLE staging_ems_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,  -- EMS 원본 데이터 전체 (JSON/CSV 변환)
  import_status TEXT DEFAULT 'pending',  -- 'pending' | 'processing' | 'completed' | 'failed'
  error_message TEXT,  -- 실패 시 오류 메시지
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_ems_status (company_id, import_status),
  INDEX idx_staging_ems_imported (imported_at)
);

-- ERP: 연료·차량, 구매 등
CREATE TABLE staging_erp_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,
  import_status TEXT DEFAULT 'pending',
  error_message TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_erp_status (company_id, import_status),
  INDEX idx_staging_erp_imported (imported_at)
);

-- EHS: 냉매, 안전·보건 등
CREATE TABLE staging_ehs_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,
  import_status TEXT DEFAULT 'pending',
  error_message TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_ehs_status (company_id, import_status),
  INDEX idx_staging_ehs_imported (imported_at)
);

-- PLM: 제품, BOM 등
CREATE TABLE staging_plm_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,
  import_status TEXT DEFAULT 'pending',
  error_message TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_plm_status (company_id, import_status),
  INDEX idx_staging_plm_imported (imported_at)
);

-- SRM: 물류, 원료, 협력회사 등
CREATE TABLE staging_srm_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,
  import_status TEXT DEFAULT 'pending',
  error_message TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_srm_status (company_id, import_status),
  INDEX idx_staging_srm_imported (imported_at)
);

-- HR: 출장·통근, 인력 등
CREATE TABLE staging_hr_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,
  import_status TEXT DEFAULT 'pending',
  error_message TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_hr_status (company_id, import_status),
  INDEX idx_staging_hr_imported (imported_at)
);

-- MDG: 마스터 데이터(배출계수 등) 등
CREATE TABLE staging_mdg_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  source_file_name TEXT,
  raw_data JSONB NOT NULL,
  import_status TEXT DEFAULT 'pending',
  error_message TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  INDEX idx_staging_mdg_status (company_id, import_status),
  INDEX idx_staging_mdg_imported (imported_at)
);

-- 레이어 2: 검증된 데이터 (Validated)
CREATE TABLE validated_ghg_activity_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  staging_id UUID,  -- 원본 스테이징 행 PK (해당 시스템 스테이징 테이블 참조)
  staging_source TEXT NOT NULL,  -- 'ems' | 'erp' | 'ehs' | 'plm' | 'srm' | 'hr' | 'mdg'
  
  -- 검증된 필드들
  tab_type TEXT NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  -- 탭별 데이터 (ghg_activity_data와 동일한 구조)
  -- ...
  
  validation_status TEXT,  -- 'valid', 'warning', 'error'
  validation_errors JSONB,
  validated_at TIMESTAMPTZ,
  validated_by TEXT,
  
  INDEX idx_validated_status (company_id, validation_status)
);

-- 레이어 3: 최종 사용 데이터 (현재 설계 유지)
CREATE TABLE ghg_activity_data (
  -- 현재 설계와 동일 (Single Table Inheritance)
  -- ...
);
```

**장점**:
- **시스템별 분리**: EMS·ERP·EHS·PLM·SRM·HR·MDG 각각 원본 전체 보존, 시스템 단위 로드/재처리 가능
- 원본 데이터 보존 (재처리 가능)
- 오류 추적 용이 (테이블·행 단위로 실패 원인 파악)
- 데이터 변환 과정 추적 가능 (`staging_source` + `staging_id`로 원본 참조)
- 원본 데이터 백업 및 복구 용이

**스테이징 → ghg_activity_data 변환: CTE + UNION ALL**

세 스테이징 테이블(`staging_ems_data`, `staging_erp_data`, `staging_ehs_data`)은 **JOIN으로 한 행을 만드는 것이 아니라**, 각각 파싱한 결과를 **행 단위로 이어 붙여** `ghg_activity_data`에 넣습니다. 구현 시 **CTE로 가상 테이블을 만든 뒤 UNION ALL로 조합**하는 방식을 사용합니다.

- **JOIN을 쓰지 않는 이유**: EMS/ERP/EHS는 서로 다른 `tab_type`(전력·열·스팀, 연료·차량, 냉매 등)의 **여러 행**을 만듦. 같은 키(company_id, period)로 1:1로 맞추면 안 되고, 각 소스에서 나온 **여러 행을 합쳐서** 한 테이블에 적재해야 함.
- **UNION ALL을 쓰는 이유**: 세 스테이징에서 파싱된 행들은 컬럼 구조를 `ghg_activity_data`에 맞춰 통일한 뒤, **이어 붙이기(UNION ALL)** 하면 됨.

```sql
-- 개념: 세 스테이징을 CTE로 파싱한 뒤 UNION ALL로 조합 → ghg_activity_data에 INSERT
-- (실제 컬럼은 ghg_activity_data 스키마에 맞춰 동일한 목록으로 맞춤. 아래는 구조 예시.)
WITH
  parsed_ems AS (
    SELECT
      s.company_id,
      (t->>'period_year')::int AS period_year,
      (t->>'period_month')::int AS period_month,
      'power_heat_steam' AS tab_type,
      t->>'site_name' AS site_name,
      t->>'energy_type' AS energy_type,
      (t->>'usage_amount')::decimal AS usage_amount,
      t->>'usage_unit' AS usage_unit,
      (t->>'renewable_ratio')::decimal AS renewable_ratio,
      'EMS' AS source_system,
      s.id AS staging_id
    FROM staging_ems_data s,
         LATERAL jsonb_array_elements(s.raw_data->'items') AS t
    WHERE s.import_status = 'completed'
  ),
  parsed_erp AS (
    SELECT
      s.company_id,
      (t->>'period_year')::int AS period_year,
      (t->>'period_month')::int AS period_month,
      'fuel_vehicle' AS tab_type,
      t->>'site_name' AS site_name,
      t->>'fuel_type' AS energy_type,  -- UNION용 동일 컬럼명
      (t->>'consumption_amount')::decimal AS usage_amount,
      t->>'fuel_unit' AS usage_unit,
      NULL::decimal AS renewable_ratio,
      'ERP' AS source_system,
      s.id AS staging_id
    FROM staging_erp_data s,
         LATERAL jsonb_array_elements(s.raw_data->'items') AS t
    WHERE s.import_status = 'completed'
  ),
  parsed_ehs AS (
    SELECT
      s.company_id,
      (t->>'period_year')::int AS period_year,
      (t->>'period_month')::int AS period_month,
      'refrigerant' AS tab_type,
      t->>'site_name' AS site_name,
      t->>'refrigerant_type' AS energy_type,  -- UNION용 동일 컬럼명
      (t->>'leak_amount_kg')::decimal AS usage_amount,
      'kg' AS usage_unit,
      NULL::decimal AS renewable_ratio,
      'EHS' AS source_system,
      s.id AS staging_id
    FROM staging_ehs_data s,
         LATERAL jsonb_array_elements(s.raw_data->'items') AS t
    WHERE s.import_status = 'completed'
  )
-- UNION ALL로 세 소스의 행을 한 결과셋으로 조합 (JOIN 아님)
SELECT * FROM parsed_ems
UNION ALL
SELECT * FROM parsed_erp
UNION ALL
SELECT * FROM parsed_ehs;
-- ↑ 이 결과를 INSERT INTO ghg_activity_data (...) 또는 validated_ghg_activity_data에 적재
-- (실제 INSERT 시에는 ghg_activity_data의 전체 컬럼 목록에 맞춰 매핑)
```

**요약**: `ghg_activity_data`에 필요한 데이터는 위 세 스테이징에서 오며, **CTE로 각 스테이징을 파싱한 뒤 UNION ALL로 조합**하여 적재합니다. 세 스테이징을 서로 **JOIN하지 않습니다**.

**스테이징 → social_data 변환: CTE + JOIN**

`social_data`(임직원·안전보건·협력회사·사회공헌)는 회사·기간당 **1행**입니다. 따라서 `staging_hr_data`(인력·출장·통근), `staging_srm_data`(협력회사), 필요 시 `staging_ehs_data`(안전·보건)에서 파싱한 결과를 **UNION ALL이 아니라 (company_id, period_year) 기준 JOIN**으로 한 행에 모아 적재합니다.

- **JOIN을 쓰는 이유**: HR은 인력·안전 컬럼, SRM은 협력회사 컬럼을 채움. 같은 회사·기간에 대해 **한 행의 서로 다른 컬럼**을 합쳐야 하므로 JOIN이 맞음.
- **UNION ALL을 쓰지 않는 이유**: UNION ALL은 행을 이어 붙이는 것. social_data는 행을 추가하는 게 아니라 **한 행을 여러 소스 컬럼으로 채우는** 구조임.

```sql
-- 개념: 스테이징 2개(HR, SRM)를 CTE로 파싱·집계한 뒤 JOIN → social_data 1행 조립
WITH
  parsed_hr AS (
    SELECT
      company_id,
      (raw_data->>'period_year')::int AS period_year,
      (raw_data->>'total_employees')::int AS total_employees,
      (raw_data->>'male_employees')::int AS male_employees,
      (raw_data->>'female_employees')::int AS female_employees,
      (raw_data->>'safety_training_hours')::decimal AS safety_training_hours,
      (raw_data->>'total_incidents')::int AS total_incidents
      -- 필요 시 추가 컬럼
    FROM staging_hr_data,
         LATERAL jsonb_array_elements(raw_data->'items') AS t
    WHERE import_status = 'completed'
    -- 회사·기간별 1행이 되도록 집계 또는 DISTINCT ON
  ),
  parsed_srm AS (
    SELECT
      company_id,
      (raw_data->>'period_year')::int AS period_year,
      (raw_data->>'total_suppliers')::int AS total_suppliers,
      (raw_data->>'supplier_purchase_amount')::decimal AS supplier_purchase_amount,
      (raw_data->>'esg_evaluated_suppliers')::int AS esg_evaluated_suppliers
    FROM staging_srm_data,
         LATERAL jsonb_array_elements(raw_data->'items') AS t
    WHERE import_status = 'completed'
  )
-- JOIN으로 한 행에 HR 컬럼 + SRM 컬럼 조립 (UNION ALL 아님)
SELECT
  COALESCE(hr.company_id, srm.company_id) AS company_id,
  COALESCE(hr.period_year, srm.period_year) AS period_year,
  hr.total_employees,
  hr.male_employees,
  hr.female_employees,
  hr.safety_training_hours,
  hr.total_incidents,
  srm.total_suppliers,
  srm.supplier_purchase_amount,
  srm.esg_evaluated_suppliers
FROM parsed_hr hr
FULL OUTER JOIN parsed_srm srm
  ON srm.company_id = hr.company_id AND srm.period_year = hr.period_year;
-- ↑ 이 결과를 INSERT INTO social_data (...) 또는 MERGE/UPDATE
```

**요약**: `social_data`에 필요한 데이터는 `staging_hr_data`, `staging_srm_data`(및 필요 시 `staging_ehs_data`)에서 오며, **CTE로 파싱·집계한 뒤 같은 키로 JOIN**하여 회사·기간당 1행을 조립해 적재합니다. **UNION ALL이 아닌 JOIN**을 사용합니다.

#### 옵션 2: 소스별 별도 테이블 패턴

각 외부 시스템별로 별도 테이블을 두고, 이후 통합 테이블로 변환하는 방식입니다.

```sql
-- ERP 데이터 전용 테이블
CREATE TABLE erp_fuel_purchase (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  purchase_date DATE,
  fuel_type TEXT,
  quantity DECIMAL(18, 4),
  unit TEXT,
  -- ERP 원본 필드 그대로 저장
  raw_data JSONB,  -- 원본 데이터 백업
  synced_at TIMESTAMPTZ,
  
  INDEX idx_erp_company_date (company_id, purchase_date)
);

-- EMS 데이터 전용 테이블
CREATE TABLE ems_energy_usage (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  usage_date DATE,
  energy_type TEXT,
  amount DECIMAL(18, 4),
  -- EMS 원본 필드 그대로 저장
  raw_data JSONB,
  synced_at TIMESTAMPTZ,
  
  INDEX idx_ems_company_date (company_id, usage_date)
);

-- 이후 통합 테이블로 변환
CREATE TABLE ghg_activity_data (
  -- 통합된 구조 (현재 설계)
  -- ...
);
```

**장점**:
- 소스별 원본 데이터 보존
- 변환 로직 분리 용이
- 소스별 특화 인덱스 최적화 가능

#### 옵션 3: 데이터 웨어하우스 패턴 (Star Schema)

Fact 테이블과 Dimension 테이블로 구성하는 방식입니다.

```sql
-- Fact 테이블 (측정값)
CREATE TABLE fact_ghg_activity (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_id UUID NOT NULL,
  period_id UUID NOT NULL,
  activity_type_id UUID NOT NULL,
  
  amount DECIMAL(18, 4),
  unit TEXT,
  emission_factor_id UUID,
  calculated_emission DECIMAL(18, 4),
  
  created_at TIMESTAMPTZ,
  
  FOREIGN KEY (site_id) REFERENCES dim_site(id),
  FOREIGN KEY (period_id) REFERENCES dim_period(id),
  FOREIGN KEY (activity_type_id) REFERENCES dim_activity_type(id),
  FOREIGN KEY (emission_factor_id) REFERENCES dim_emission_factor(id)
);

-- Dimension 테이블들
CREATE TABLE dim_activity_type (
  id UUID PRIMARY KEY,
  type_code TEXT NOT NULL UNIQUE,  -- 'power_heat_steam', 'fuel_vehicle' 등
  type_name TEXT,
  scope TEXT,  -- 'Scope1', 'Scope2', 'Scope3'
  category TEXT
);

CREATE TABLE dim_site (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT,
  site_code TEXT,
  address TEXT
);

CREATE TABLE dim_period (
  id UUID PRIMARY KEY,
  period_year INTEGER,
  period_month INTEGER,
  period_quarter INTEGER,
  period_start_date DATE,
  period_end_date DATE,
  period_type TEXT  -- 'monthly', 'quarterly', 'yearly'
);

CREATE TABLE dim_emission_factor (
  id UUID PRIMARY KEY,
  factor_code TEXT NOT NULL UNIQUE,
  factor_name_ko TEXT,
  emission_factor DECIMAL(18, 6),
  unit TEXT,
  reference_year INTEGER
);
```

**장점**:
- 정규화된 구조
- 분석 쿼리 최적화
- Dimension 재사용 가능

**단점**:
- JOIN이 많아져 복잡도 증가
- 현재 설계 대비 변경 폭 큼

### 6.4 구현 우선순위

#### Phase 1: 스테이징 테이블 추가 (우선 권장)

1. **스테이징 테이블 생성 (시스템별 7개)**
   - `staging_ems_data` — EMS 원본 데이터 전체
   - `staging_erp_data` — ERP 원본 데이터 전체
   - `staging_ehs_data` — EHS 원본 데이터 전체
   - `staging_plm_data` — PLM 원본 데이터 전체
   - `staging_srm_data` — SRM 원본 데이터 전체
   - `staging_hr_data` — HR 원본 데이터 전체
   - `staging_mdg_data` — MDG 원본 데이터 전체

2. **ETL 프로세스 구현**
   - Extract: 외부 시스템에서 데이터 수집
   - Transform: 스테이징 → 검증 → 최종 변환.
     - **스테이징 3개(EMS/ERP/EHS) → ghg_activity_data**: CTE로 파싱한 뒤 **UNION ALL**로 조합 (JOIN 사용 안 함). 상세는 [옵션 1](#옵션-1-스테이징-테이블-패턴-권장) 내 "스테이징 → ghg_activity_data 변환: CTE + UNION ALL" 참고.
     - **스테이징(HR/SRM 등) → social_data**: CTE로 파싱·집계한 뒤 **(company_id, period_year) 기준 JOIN**으로 한 행 조립 (UNION ALL 아님). 상세는 [옵션 1](#옵션-1-스테이징-테이블-패턴-권장) 내 "스테이징 → social_data 변환: CTE + JOIN" 참고.
   - Load: `ghg_activity_data`, `social_data` 등 대상 테이블에 저장

3. **오류 처리 및 재처리**
   - 실패한 데이터 추적
   - 재처리 기능

#### Phase 2: 검증 레이어 추가

1. **검증 테이블 생성**
   - `validated_ghg_activity_data`

2. **검증 규칙 구현**
   - 필수 필드 검증
   - 데이터 타입 검증
   - 비즈니스 로직 검증

#### Phase 3: 모니터링 및 추적

1. **데이터 계보 추적**
   - 원본 → 스테이징 → 검증 → 최종 추적

2. **변환 로그**
   - 변환 과정 기록
   - 변환 오류 로그

### 6.5 현재 설계와의 호환성

**현재 `ghg_activity_data` 테이블 구조는 유지**하고, 앞단에 스테이징 레이어를 추가하는 방식이 가장 적합합니다.

```
[외부 시스템] 
    ↓
[스테이징 테이블] ← 새로 추가
    ↓
[검증 테이블] ← 새로 추가 (선택)
    ↓
[ghg_activity_data] ← 현재 설계 유지
```

이렇게 하면:
- 기존 설계 변경 최소화
- 데이터 수집 프로세스 개선
- 원본 데이터 보존 및 추적 가능

### 6.6 테이블 구조 개선: 6개 테이블 분리 + 통합 뷰

#### 6.6.1 현재 설계의 문제점

현재 `ghg_activity_data` 테이블은 Single Table Inheritance 패턴을 사용하고 있어:
- 많은 NULL 컬럼 발생 (tab_type에 따라 사용하지 않는 필드가 NULL)
- 스키마가 비대해짐
- 탭별 필수 필드 검증이 복잡
- 탭별 인덱스 최적화 어려움

#### 6.6.2 개선안: 6개 테이블 분리 + 통합 뷰

각 탭을 별도 테이블로 분리하고, 통합 조회를 위한 뷰를 생성하는 방식입니다.

**장점**:
- NULL 제거: 각 테이블은 해당 탭 필드만 포함
- 스키마 명확성: 탭별 스키마가 명확하고 필수 필드 검증이 쉬움
- 인덱스 최적화: 탭별 특화 인덱스 가능
- 확장성: 탭별 필드 추가가 독립적
- 유지보수: 탭별 독립적 수정 가능

**단점**:
- 통합 조회 시 UNION 필요 (하지만 뷰로 해결)
- 초기 마이그레이션 필요

#### 6.6.3 개선된 테이블 구조

```sql
-- 1. 각 탭별 테이블 생성

-- 전력·열·스팀 테이블
CREATE TABLE ghg_power_heat_steam_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  energy_type TEXT NOT NULL,  -- '전력' | '열' | '스팀'
  energy_source TEXT,  -- '한국전력' | '지역난방' 등
  usage_amount DECIMAL(18, 4) NOT NULL,
  usage_unit TEXT NOT NULL,  -- 'kWh' | 'Gcal' | 'GJ'
  renewable_ratio DECIMAL(5, 2),  -- 재생에너지 비율 (%)
  
  data_quality TEXT,  -- 'M1' | 'M2' | 'E1' | 'E2'
  source_system TEXT,  -- 'EMS' | 'manual'
  synced_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_power_company (company_id, period_year, period_month),
  INDEX idx_power_site (company_id, site_name, period_year),
  INDEX idx_power_energy_type (company_id, energy_type)
);

-- 연료·차량 테이블
CREATE TABLE ghg_fuel_vehicle_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  fuel_category TEXT NOT NULL,  -- '고정연소' | '이동연소'
  fuel_type TEXT NOT NULL,  -- 'LNG' | '경유' | '휘발유' 등
  consumption_amount DECIMAL(18, 4) NOT NULL,
  fuel_unit TEXT NOT NULL,  -- 'Nm³' | 'L' | 'kg'
  purchase_amount DECIMAL(18, 4),
  
  data_quality TEXT,
  source_system TEXT,  -- 'ERP' | 'manual'
  synced_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_fuel_company (company_id, period_year, period_month),
  INDEX idx_fuel_category (company_id, fuel_category)
);

-- 냉매 테이블
CREATE TABLE ghg_refrigerant_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  equipment_id TEXT NOT NULL,
  equipment_type TEXT,  -- '에어컨' | '냉동기' | '칠러'
  refrigerant_type TEXT NOT NULL,  -- 'HFC-134a' | 'HFC-410A' 등
  charge_amount_kg DECIMAL(18, 4),
  leak_amount_kg DECIMAL(18, 4) NOT NULL,
  gwp_factor DECIMAL(18, 4),
  inspection_date DATE,
  
  data_quality TEXT,
  source_system TEXT,  -- 'EHS' | 'manual'
  synced_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_refrigerant_company (company_id, period_year, period_month),
  INDEX idx_refrigerant_equipment (company_id, equipment_id)
);

-- 폐기물 테이블
CREATE TABLE ghg_waste_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  waste_type TEXT NOT NULL,  -- '일반' | '지정' | '건설'
  waste_name TEXT,
  generation_amount DECIMAL(18, 4) NOT NULL,  -- 발생량 (톤)
  disposal_method TEXT NOT NULL,  -- '소각' | '매립' | '재활용' | '위탁'
  incineration_amount DECIMAL(18, 4),  -- 소각량 (톤)
  recycling_amount DECIMAL(18, 4),  -- 재활용량 (톤)
  
  data_quality TEXT,
  source_system TEXT,  -- 'EMS' | 'manual'
  synced_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_waste_company (company_id, period_year, period_month),
  INDEX idx_waste_disposal (company_id, disposal_method)
);

-- 물류·출장·통근 테이블
CREATE TABLE ghg_logistics_travel_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  category TEXT NOT NULL,  -- '물류(인바운드)' | '물류(아웃바운드)' | '출장' | '통근'
  transport_mode TEXT NOT NULL,  -- '항공' | '해상' | '도로' | '철도' | '자가용'
  origin_country TEXT,
  destination_country TEXT,
  distance_km DECIMAL(18, 4) NOT NULL,
  weight_ton DECIMAL(18, 4),  -- 물류용
  person_trips INTEGER,  -- 출장·통근용
  
  data_quality TEXT,
  source_system TEXT,  -- 'SRM' | 'HR' | 'manual'
  synced_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_logistics_company (company_id, period_year, period_month),
  INDEX idx_logistics_category (company_id, category)
);

-- 원료·제품 테이블
CREATE TABLE ghg_raw_materials_data (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  period_year INTEGER NOT NULL,
  period_month INTEGER,
  
  supplier_name TEXT,
  product_name TEXT,
  supplier_emission_tco2e DECIMAL(18, 4),
  use_phase_emission DECIMAL(18, 4),
  eol_emission DECIMAL(18, 4),
  ghg_reported_yn TEXT,  -- '직접보고' | '추정'
  
  data_quality TEXT,
  source_system TEXT,  -- 'SRM' | 'PLM' | 'manual'
  synced_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_raw_company (company_id, period_year, period_month),
  INDEX idx_raw_supplier (company_id, supplier_name)
);

-- 2. 통합 뷰 생성 (통합 조회용)
CREATE VIEW ghg_activity_data_unified AS
SELECT 
  id,
  company_id,
  'power_heat_steam' AS tab_type,
  site_name,
  period_year,
  period_month,
  -- 전력·열·스팀 필드
  energy_type,
  energy_source,
  usage_amount,
  usage_unit,
  renewable_ratio,
  -- 나머지 탭 필드는 NULL
  NULL AS fuel_category,
  NULL AS fuel_type,
  NULL AS consumption_amount,
  NULL AS fuel_unit,
  NULL AS purchase_amount,
  NULL AS equipment_id,
  NULL AS equipment_type,
  NULL AS refrigerant_type,
  NULL AS charge_amount_kg,
  NULL AS leak_amount_kg,
  NULL AS gwp_factor,
  NULL AS inspection_date,
  NULL AS waste_type,
  NULL AS waste_name,
  NULL AS generation_amount,
  NULL AS disposal_method,
  NULL AS incineration_amount,
  NULL AS recycling_amount,
  NULL AS category,
  NULL AS transport_mode,
  NULL AS origin_country,
  NULL AS destination_country,
  NULL AS distance_km,
  NULL AS weight_ton,
  NULL AS person_trips,
  NULL AS supplier_name,
  NULL AS product_name,
  NULL AS supplier_emission_tco2e,
  NULL AS use_phase_emission,
  NULL AS eol_emission,
  NULL AS ghg_reported_yn,
  data_quality,
  source_system,
  synced_at,
  updated_at,
  created_at
FROM ghg_power_heat_steam_data

UNION ALL

SELECT 
  id,
  company_id,
  'fuel_vehicle' AS tab_type,
  site_name,
  period_year,
  period_month,
  -- 전력 필드는 NULL
  NULL AS energy_type,
  NULL AS energy_source,
  NULL AS usage_amount,
  NULL AS usage_unit,
  NULL AS renewable_ratio,
  -- 연료 필드
  fuel_category,
  fuel_type,
  consumption_amount,
  fuel_unit,
  purchase_amount,
  -- 나머지는 NULL
  NULL AS equipment_id,
  NULL AS equipment_type,
  NULL AS refrigerant_type,
  NULL AS charge_amount_kg,
  NULL AS leak_amount_kg,
  NULL AS gwp_factor,
  NULL AS inspection_date,
  NULL AS waste_type,
  NULL AS waste_name,
  NULL AS generation_amount,
  NULL AS disposal_method,
  NULL AS incineration_amount,
  NULL AS recycling_amount,
  NULL AS category,
  NULL AS transport_mode,
  NULL AS origin_country,
  NULL AS destination_country,
  NULL AS distance_km,
  NULL AS weight_ton,
  NULL AS person_trips,
  NULL AS supplier_name,
  NULL AS product_name,
  NULL AS supplier_emission_tco2e,
  NULL AS use_phase_emission,
  NULL AS eol_emission,
  NULL AS ghg_reported_yn,
  data_quality,
  source_system,
  synced_at,
  updated_at,
  created_at
FROM ghg_fuel_vehicle_data

UNION ALL

SELECT 
  id,
  company_id,
  'refrigerant' AS tab_type,
  site_name,
  period_year,
  period_month,
  NULL AS energy_type,
  NULL AS energy_source,
  NULL AS usage_amount,
  NULL AS usage_unit,
  NULL AS renewable_ratio,
  NULL AS fuel_category,
  NULL AS fuel_type,
  NULL AS consumption_amount,
  NULL AS fuel_unit,
  NULL AS purchase_amount,
  equipment_id,
  equipment_type,
  refrigerant_type,
  charge_amount_kg,
  leak_amount_kg,
  gwp_factor,
  inspection_date,
  NULL AS waste_type,
  NULL AS waste_name,
  NULL AS generation_amount,
  NULL AS disposal_method,
  NULL AS incineration_amount,
  NULL AS recycling_amount,
  NULL AS category,
  NULL AS transport_mode,
  NULL AS origin_country,
  NULL AS destination_country,
  NULL AS distance_km,
  NULL AS weight_ton,
  NULL AS person_trips,
  NULL AS supplier_name,
  NULL AS product_name,
  NULL AS supplier_emission_tco2e,
  NULL AS use_phase_emission,
  NULL AS eol_emission,
  NULL AS ghg_reported_yn,
  data_quality,
  source_system,
  synced_at,
  updated_at,
  created_at
FROM ghg_refrigerant_data

UNION ALL

SELECT 
  id,
  company_id,
  'waste' AS tab_type,
  site_name,
  period_year,
  period_month,
  NULL AS energy_type,
  NULL AS energy_source,
  NULL AS usage_amount,
  NULL AS usage_unit,
  NULL AS renewable_ratio,
  NULL AS fuel_category,
  NULL AS fuel_type,
  NULL AS consumption_amount,
  NULL AS fuel_unit,
  NULL AS purchase_amount,
  NULL AS equipment_id,
  NULL AS equipment_type,
  NULL AS refrigerant_type,
  NULL AS charge_amount_kg,
  NULL AS leak_amount_kg,
  NULL AS gwp_factor,
  NULL AS inspection_date,
  waste_type,
  waste_name,
  generation_amount,
  disposal_method,
  incineration_amount,
  recycling_amount,
  NULL AS category,
  NULL AS transport_mode,
  NULL AS origin_country,
  NULL AS destination_country,
  NULL AS distance_km,
  NULL AS weight_ton,
  NULL AS person_trips,
  NULL AS supplier_name,
  NULL AS product_name,
  NULL AS supplier_emission_tco2e,
  NULL AS use_phase_emission,
  NULL AS eol_emission,
  NULL AS ghg_reported_yn,
  data_quality,
  source_system,
  synced_at,
  updated_at,
  created_at
FROM ghg_waste_data

UNION ALL

SELECT 
  id,
  company_id,
  'logistics_travel' AS tab_type,
  site_name,
  period_year,
  period_month,
  NULL AS energy_type,
  NULL AS energy_source,
  NULL AS usage_amount,
  NULL AS usage_unit,
  NULL AS renewable_ratio,
  NULL AS fuel_category,
  NULL AS fuel_type,
  NULL AS consumption_amount,
  NULL AS fuel_unit,
  NULL AS purchase_amount,
  NULL AS equipment_id,
  NULL AS equipment_type,
  NULL AS refrigerant_type,
  NULL AS charge_amount_kg,
  NULL AS leak_amount_kg,
  NULL AS gwp_factor,
  NULL AS inspection_date,
  NULL AS waste_type,
  NULL AS waste_name,
  NULL AS generation_amount,
  NULL AS disposal_method,
  NULL AS incineration_amount,
  NULL AS recycling_amount,
  category,
  transport_mode,
  origin_country,
  destination_country,
  distance_km,
  weight_ton,
  person_trips,
  NULL AS supplier_name,
  NULL AS product_name,
  NULL AS supplier_emission_tco2e,
  NULL AS use_phase_emission,
  NULL AS eol_emission,
  NULL AS ghg_reported_yn,
  data_quality,
  source_system,
  synced_at,
  updated_at,
  created_at
FROM ghg_logistics_travel_data

UNION ALL

SELECT 
  id,
  company_id,
  'raw_materials' AS tab_type,
  site_name,
  period_year,
  period_month,
  NULL AS energy_type,
  NULL AS energy_source,
  NULL AS usage_amount,
  NULL AS usage_unit,
  NULL AS renewable_ratio,
  NULL AS fuel_category,
  NULL AS fuel_type,
  NULL AS consumption_amount,
  NULL AS fuel_unit,
  NULL AS purchase_amount,
  NULL AS equipment_id,
  NULL AS equipment_type,
  NULL AS refrigerant_type,
  NULL AS charge_amount_kg,
  NULL AS leak_amount_kg,
  NULL AS gwp_factor,
  NULL AS inspection_date,
  NULL AS waste_type,
  NULL AS waste_name,
  NULL AS generation_amount,
  NULL AS disposal_method,
  NULL AS incineration_amount,
  NULL AS recycling_amount,
  NULL AS category,
  NULL AS transport_mode,
  NULL AS origin_country,
  NULL AS destination_country,
  NULL AS distance_km,
  NULL AS weight_ton,
  NULL AS person_trips,
  supplier_name,
  product_name,
  supplier_emission_tco2e,
  use_phase_emission,
  eol_emission,
  ghg_reported_yn,
  data_quality,
  source_system,
  synced_at,
  updated_at,
  created_at
FROM ghg_raw_materials_data;
```

#### 6.6.4 사용 방법

**탭별 조회 (개별 테이블 사용)**:
```sql
-- 전력 데이터만 조회
SELECT * FROM ghg_power_heat_steam_data 
WHERE company_id = 'company-001' 
  AND period_year = 2024 
  AND period_month = 1;

-- 연료 데이터만 조회
SELECT * FROM ghg_fuel_vehicle_data 
WHERE company_id = 'company-001' 
  AND period_year = 2024;
```

**통합 조회 (뷰 사용)**:
```sql
-- 모든 탭 데이터 통합 조회
SELECT * FROM ghg_activity_data_unified 
WHERE company_id = 'company-001' 
  AND period_year = 2024 
  AND period_month = 1;

-- 탭별 집계
SELECT tab_type, COUNT(*) 
FROM ghg_activity_data_unified 
WHERE company_id = 'company-001' 
  AND period_year = 2024 
GROUP BY tab_type;
```

**데이터 입력 (개별 테이블에 직접)**:
```sql
-- 전력 데이터 입력
INSERT INTO ghg_power_heat_steam_data 
(company_id, site_name, period_year, period_month, 
 energy_type, usage_amount, usage_unit)
VALUES ('company-001', '서울본사', 2024, 1, '전력', 125000, 'kWh');

-- 연료 데이터 입력
INSERT INTO ghg_fuel_vehicle_data 
(company_id, site_name, period_year, period_month,
 fuel_category, fuel_type, consumption_amount, fuel_unit)
VALUES ('company-001', '서울본사', 2024, 1, '고정연소', 'LNG', 85000, 'Nm³');
```

#### 6.6.5 마이그레이션 전략

현재 설계에서 개선 설계로 전환하는 방법:

```sql
-- 1단계: 새 테이블 생성
CREATE TABLE ghg_power_heat_steam_data (...);
CREATE TABLE ghg_fuel_vehicle_data (...);
CREATE TABLE ghg_refrigerant_data (...);
CREATE TABLE ghg_waste_data (...);
CREATE TABLE ghg_logistics_travel_data (...);
CREATE TABLE ghg_raw_materials_data (...);

-- 2단계: 기존 데이터 마이그레이션
INSERT INTO ghg_power_heat_steam_data
SELECT id, company_id, site_name, period_year, period_month,
       energy_type, energy_source, usage_amount, usage_unit, renewable_ratio,
       data_quality, source_system, synced_at, updated_at, created_at
FROM ghg_activity_data
WHERE tab_type = 'power_heat_steam';

INSERT INTO ghg_fuel_vehicle_data
SELECT id, company_id, site_name, period_year, period_month,
       fuel_category, fuel_type, consumption_amount, fuel_unit, purchase_amount,
       data_quality, source_system, synced_at, updated_at, created_at
FROM ghg_activity_data
WHERE tab_type = 'fuel_vehicle';

-- ... 나머지 4개 탭도 동일하게

-- 3단계: 통합 뷰 생성
CREATE VIEW ghg_activity_data_unified AS ...;

-- 4단계: 애플리케이션 코드 수정
-- - 탭별 테이블에 직접 INSERT/UPDATE
-- - 통합 조회는 뷰 사용
-- - 기존 ghg_activity_data 테이블 참조 제거

-- 5단계: 기존 테이블 백업 후 제거 (선택)
-- ALTER TABLE ghg_activity_data RENAME TO ghg_activity_data_old;
-- 또는
-- DROP TABLE ghg_activity_data;
```

#### 6.6.6 구현 우선순위

**Phase 1: 테이블 분리 (우선 권장)**
1. 6개 탭별 테이블 생성
2. 통합 뷰 생성
3. 애플리케이션 코드 수정 (탭별 테이블 사용)

**Phase 2: 데이터 마이그레이션**
1. 기존 데이터 마이그레이션 스크립트 작성
2. 데이터 검증
3. 기존 테이블 제거 또는 백업

**Phase 3: 최적화**
1. 탭별 인덱스 최적화
2. 통합 뷰 성능 튜닝
3. 모니터링 및 성능 측정

---

## 7. 대시보드 및 시스템 관리 테이블

### 7.1 진행률 집계 테이블

#### `page_progress` - 페이지별 진행 상태

**역할**: 각 페이지(회사정보, GHG 산정, SR 작성, 도표 생성)의 진행 상태 및 완료율 추적

**주요 필드**:
```sql
CREATE TABLE page_progress (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 페이지 정보
  page_type TEXT NOT NULL,  -- 'company_info' | 'ghg' | 'sr' | 'charts'
  page_name_ko TEXT NOT NULL,  -- '회사정보' | 'GHG 산정' | 'SR 작성' | '도표 생성'
  
  -- 진행 상태
  status TEXT NOT NULL DEFAULT 'waiting',  -- 'waiting' | 'in_progress' | 'completed'
  progress_percent INTEGER DEFAULT 0,  -- 0~100
  
  -- 담당자 정보
  assignee_id UUID REFERENCES users(id),  -- 담당 팀원
  assignee_name TEXT,  -- 담당자 이름 (스냅샷)
  
  -- 완료 정보
  completed_at TIMESTAMPTZ,
  completed_by UUID REFERENCES users(id),
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_page_progress_company (company_id, page_type),
  INDEX idx_page_progress_status (company_id, status),
  INDEX idx_page_progress_assignee (assignee_id),
  
  CONSTRAINT chk_page_type CHECK (
    page_type IN ('company_info', 'ghg', 'sr', 'charts')
  ),
  CONSTRAINT chk_status CHECK (
    status IN ('waiting', 'in_progress', 'completed')
  ),
  CONSTRAINT chk_progress_percent CHECK (
    progress_percent >= 0 AND progress_percent <= 100
  ),
  
  UNIQUE(company_id, page_type)  -- 회사별 페이지는 하나만
);
```

**자동 진행률 계산 로직**:
- `company_info`: `company_info.submitted_to_final_report = TRUE` → 100%
- `ghg`: `ghg_calculation_snapshots.is_locked = TRUE` → 100%
- `sr`: `sr_report_content.saved_to_final_report = TRUE` 항목 수 / 전체 항목 수
- `charts`: `esg_charts.saved_to_final_report = TRUE` 항목 수 / 전체 항목 수

---

#### `progress_snapshots` - 진행률 스냅샷

**역할**: 특정 시점의 진행률 스냅샷 저장 (이력 추적)

**주요 필드**:
```sql
CREATE TABLE progress_snapshots (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 스냅샷 정보
  snapshot_date DATE NOT NULL,  -- 스냅샷 날짜
  overall_progress INTEGER DEFAULT 0,  -- 전체 진행률 (0~100)
  
  -- 페이지별 진행률 (JSONB)
  page_progress_data JSONB NOT NULL,  -- {"company_info": 100, "ghg": 75, "sr": 50, "charts": 25}
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_progress_snapshots_company (company_id, snapshot_date),
  
  UNIQUE(company_id, snapshot_date)  -- 회사별 날짜는 하나만
);
```

---

### 7.2 알림 관리 테이블

#### `notifications` - 인앱 알림

**역할**: 사용자별 알림 메시지 저장 및 읽음 상태 관리 (인앱 + 이메일)

**주요 필드**:
```sql
CREATE TABLE notifications (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  user_id UUID NOT NULL REFERENCES users(id),  -- 수신자
  
  -- 알림 정보
  notification_type TEXT NOT NULL,  -- 'join_request' | 'review_request' | 'approved' | 'rejected' | 'final_approved' | 'deadline_approaching' | 'task_assigned' | 'comment_added' | 'reminder'
  title TEXT NOT NULL,  -- 알림 제목
  message TEXT NOT NULL,  -- 알림 내용
  link TEXT,  -- 클릭 시 이동할 경로 (예: '/dashboard', '/ghg/calculation')
  
  -- 템플릿 정보
  template_id UUID REFERENCES notification_templates(id),  -- 사용된 템플릿 (선택적)
  
  -- 관련 엔티티 참조 (Polymorphic Association)
  related_entity_type TEXT,  -- 'review_request' | 'todo' | 'page_progress' | 'report_export' | 'workflow_approval'
  related_entity_id UUID,  -- 관련 엔티티의 PK
  
  -- 읽음 상태
  is_read BOOLEAN DEFAULT FALSE,
  read_at TIMESTAMPTZ,
  
  -- 전송 상태 (이메일 알림용)
  delivery_status TEXT DEFAULT 'pending',  -- 'pending' | 'sent' | 'failed' | 'skipped'
  email_sent BOOLEAN DEFAULT FALSE,  -- 이메일 발송 여부
  email_sent_at TIMESTAMPTZ,  -- 이메일 발송 시각
  email_failed_reason TEXT,  -- 이메일 발송 실패 사유
  
  -- 우선순위
  priority TEXT DEFAULT 'normal',  -- 'low' | 'normal' | 'high' | 'urgent'
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_notifications_user (user_id, is_read, created_at),
  INDEX idx_notifications_company (company_id, notification_type),
  INDEX idx_notifications_related (related_entity_type, related_entity_id),
  INDEX idx_notifications_delivery (user_id, delivery_status, email_sent),
  INDEX idx_notifications_template (template_id),
  
  CONSTRAINT chk_notification_type CHECK (
    notification_type IN ('join_request', 'review_request', 'approved', 'rejected', 'final_approved', 'deadline_approaching', 'task_assigned', 'comment_added', 'reminder', 'system', 'workflow_pending')
  ),
  CONSTRAINT chk_priority CHECK (
    priority IN ('low', 'normal', 'high', 'urgent')
  ),
  CONSTRAINT chk_delivery_status CHECK (
    delivery_status IN ('pending', 'sent', 'failed', 'skipped')
  )
);
```

**알림 타입별 설명**:
- `join_request`: 팀원 가입 요청 (팀장에게)
- `review_request`: 검토 요청 (팀장에게)
- `approved`: 승인 완료 (팀원에게)
- `rejected`: 반려 (팀원에게)
- `final_approved`: 최종 보고서 승인 (전체 팀원에게)
- `deadline_approaching`: 마감일 임박 (담당자에게)
- `task_assigned`: 작업 할당 (담당자에게)
- `comment_added`: 코멘트 추가 (관련자에게)
- `reminder`: 리마인드 알림
- `workflow_pending`: 승인 워크플로우 대기
- `system`: 시스템 알림

---

#### `notification_templates` - 알림 템플릿

**역할**: 알림 메시지의 내용과 형식을 정의하는 재사용 가능한 템플릿 관리

**템플릿의 역할**:
- **"무엇을 보낼지" 정의**: 알림 메시지의 제목, 본문 형식 정의
- **일관성 유지**: 동일한 알림 타입에 대해 일관된 메시지 형식 제공
- **변수 치환**: `{{변수명}}` 형식으로 동적 내용 생성
- **채널별 형식**: 인앱, 이메일 등 채널별로 다른 형식 지원

**채널(Channel)의 의미**:
- **채널 = 알림 전달 방법** (탭이 아님)
  - `in_app`: 인앱 알림 (앱 내부에서 표시)
  - `email`: 이메일 알림 (사용자 이메일로 발송)
  - `both`: 인앱 + 이메일 둘 다
  - `slack`: 슬랙 알림 (향후 확장 가능)
  - `all`: 모든 채널

**주요 필드**:
```sql
CREATE TABLE notification_templates (
  id UUID PRIMARY KEY,
  company_id UUID REFERENCES companies(id),  -- NULL이면 시스템 기본 템플릿
  
  -- 템플릿 정보
  template_code TEXT NOT NULL UNIQUE,  -- 'review_request_email' | 'approval_notification' 등
  template_name_ko TEXT NOT NULL,  -- 템플릿 이름 (한국어)
  template_name_en TEXT,  -- 템플릿 이름 (영어)
  
  -- 알림 타입
  notification_type TEXT NOT NULL,  -- 'review_request' | 'approved' | 'rejected' 등
  channel_type TEXT NOT NULL,  -- 'in_app' | 'email' | 'both' | 'slack' | 'all'
  
  -- 템플릿 내용
  subject_template TEXT,  -- 이메일 제목 템플릿 (이메일인 경우)
  body_template TEXT NOT NULL,  -- 본문 템플릿 (인앱/이메일)
  html_template TEXT,  -- HTML 이메일 템플릿 (이메일인 경우)
  slack_template JSONB,  -- 슬랙 블록 키트 형식 (슬랙인 경우, 향후 확장)
  
  -- 변수 정보
  variables JSONB,  -- 템플릿 변수 목록 및 설명 (예: {"user_name": "사용자 이름", "page_name": "페이지 이름"})
  
  -- 활성화 상태
  is_active BOOLEAN DEFAULT TRUE,
  is_default BOOLEAN DEFAULT FALSE,  -- 기본 템플릿 여부
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_templates_code (template_code),
  INDEX idx_templates_type (notification_type, channel_type),
  INDEX idx_templates_company (company_id, is_active),
  
  CONSTRAINT chk_template_channel CHECK (
    channel_type IN ('in_app', 'email', 'slack', 'both', 'all')
  )
);
```

**템플릿 변수 예시**:
```json
{
  "requester_name": "요청자 이름",
  "page_name": "페이지 이름",
  "deadline": "마감일",
  "reviewer_name": "검토자 이름",
  "feedback": "피드백 내용",
  "link": "링크 URL"
}
```

**템플릿 사용 예시**:
```sql
-- 검토 요청 이메일 템플릿
INSERT INTO notification_templates (
  template_code,
  template_name_ko,
  notification_type,
  channel_type,
  subject_template,
  body_template,
  html_template,
  variables
) VALUES (
  'review_request_email',
  '검토 요청 이메일',
  'review_request',
  'email',
  '[검토 요청] {{page_name}} 검토 부탁드립니다',
  '{{requester_name}}님이 {{page_name}}에 대한 검토를 요청했습니다.
  
요청 내용: {{request_message}}

확인하시려면 아래 링크를 클릭하세요:
{{link}}',
  '<html>
    <body>
      <h2>검토 요청</h2>
      <p>{{requester_name}}님이 {{page_name}}에 대한 검토를 요청했습니다.</p>
      <p>{{request_message}}</p>
      <a href="{{link}}">확인하기</a>
    </body>
  </html>',
  '{
    "requester_name": "요청자 이름",
    "page_name": "페이지 이름 (예: GHG 산정)",
    "request_message": "요청 메시지",
    "link": "링크 URL"
  }'::jsonb
);
```

**템플릿이 필요한 이유**:
1. **일관성**: 동일한 알림 타입에 대해 일관된 메시지 형식 유지
2. **재사용성**: 한 번 정의하고 여러 번 사용
3. **유지보수**: 템플릿만 수정하면 모든 알림에 반영
4. **다국어 지원**: 템플릿별로 한국어/영어 버전 관리 가능
5. **회사별 커스터마이징**: 회사별로 다른 템플릿 사용 가능

**템플릿 우선순위**:
1. 회사별 커스텀 템플릿 (있으면 사용)
2. 시스템 기본 템플릿 (없으면 사용)

---

#### `notification_preferences` - 알림 설정

**역할**: 사용자별 알림 수신 설정 관리

**주요 필드**:
```sql
CREATE TABLE notification_preferences (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 알림 타입별 설정
  notification_type TEXT NOT NULL,  -- 'review_request' | 'approved' | 'rejected' 등
  
  -- 채널별 수신 설정
  in_app_enabled BOOLEAN DEFAULT TRUE,  -- 인앱 알림 수신 여부
  email_enabled BOOLEAN DEFAULT FALSE,  -- 이메일 알림 수신 여부
  slack_enabled BOOLEAN DEFAULT FALSE,  -- 슬랙 알림 수신 여부 (향후 확장)
  slack_webhook_url TEXT,  -- 슬랙 웹훅 URL (사용자 설정 기반)
  
  -- 우선순위 필터
  min_priority TEXT DEFAULT 'low',  -- 최소 우선순위 (이 이상만 수신)
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_preferences_user (user_id, notification_type),
  INDEX idx_preferences_company (company_id),
  
  UNIQUE(user_id, notification_type)  -- 사용자별 알림 타입은 하나만
);
```

**기본 설정**:
- 모든 알림 타입에 대해 인앱 알림 기본 활성화
- 이메일 알림은 사용자가 선택적으로 활성화
- 슬랙 알림은 사용자가 웹훅 URL을 설정하면 활성화

**사용 예시**:
```sql
-- 사용자가 이메일 알림 활성화
UPDATE notification_preferences
SET email_enabled = TRUE
WHERE user_id = 'user-123' AND notification_type = 'review_request';

-- 사용자가 슬랙 연동 설정
UPDATE notification_preferences
SET slack_enabled = TRUE,
    slack_webhook_url = 'https://hooks.slack.com/services/...'
WHERE user_id = 'user-123' AND notification_type = 'review_request';
```

---

#### `notification_delivery_logs` - 알림 전송 이력

**역할**: 알림 전송 이력 및 실패 추적 (이메일, 슬랙 등 외부 채널)

**주요 필드**:
```sql
CREATE TABLE notification_delivery_logs (
  id UUID PRIMARY KEY,
  notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  
  -- 전송 정보
  channel_type TEXT NOT NULL,  -- 'email' | 'slack' | 'sms' | 'push' (향후 확장)
  recipient_email TEXT,  -- 수신자 이메일 (이메일인 경우)
  recipient_phone TEXT,  -- 수신자 전화번호 (SMS인 경우)
  slack_channel TEXT,  -- 슬랙 채널명 (슬랙인 경우)
  
  -- 전송 상태
  delivery_status TEXT NOT NULL,  -- 'pending' | 'sent' | 'delivered' | 'failed' | 'bounced'
  delivery_attempts INTEGER DEFAULT 0,  -- 전송 시도 횟수
  last_attempt_at TIMESTAMPTZ,  -- 마지막 시도 시각
  
  -- 실패 정보
  failure_reason TEXT,  -- 실패 사유
  error_code TEXT,  -- 에러 코드
  error_message TEXT,  -- 에러 메시지
  
  -- 외부 서비스 정보
  external_message_id TEXT,  -- 이메일/슬랙 서비스의 메시지 ID
  external_provider TEXT,  -- 'sendgrid' | 'ses' | 'smtp' | 'slack_api' | 'slack_webhook' 등
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_delivery_logs_notification (notification_id),
  INDEX idx_delivery_logs_user (user_id, delivery_status),
  INDEX idx_delivery_logs_status (delivery_status, created_at),
  INDEX idx_delivery_logs_provider (external_provider, delivery_status),
  INDEX idx_delivery_logs_channel (channel_type, delivery_status),
  
  CONSTRAINT chk_delivery_channel CHECK (
    channel_type IN ('email', 'slack', 'sms', 'push')
  ),
  CONSTRAINT chk_delivery_status CHECK (
    delivery_status IN ('pending', 'sent', 'delivered', 'failed', 'bounced')
  )
);
```

**전송 상태 설명**:
- `pending`: 전송 대기 중
- `sent`: 전송 완료 (이메일 서버로 전송됨)
- `delivered`: 수신 확인 (이메일 수신함 도착 확인)
- `failed`: 전송 실패
- `bounced`: 반송 (이메일 주소 오류 등)

**외부 서비스 연동 예시**:
- 이메일: SendGrid, AWS SES, SMTP 서버
- 슬랙: Slack API, Slack Webhook
- 향후 확장: SMS, Push 알림 등

---

#### `reminder_schedules` - 리마인드 스케줄링

**역할**: 리마인드 알림 스케줄 관리

**주요 필드**:
```sql
CREATE TABLE reminder_schedules (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  user_id UUID NOT NULL REFERENCES users(id),  -- 리마인드 받을 사용자
  
  -- 스케줄 정보
  reminder_type TEXT NOT NULL,  -- 'deadline' | 'task' | 'review' | 'approval'
  reminder_title TEXT NOT NULL,  -- 리마인드 제목
  reminder_message TEXT,  -- 리마인드 메시지
  
  -- 스케줄 설정
  target_date DATE NOT NULL,  -- 목표 날짜 (마감일 등)
  reminder_days_before INTEGER[],  -- 목표 날짜 N일 전에 알림 (예: [7, 3, 1])
  reminder_times TIME[],  -- 알림 시간 (예: ['09:00', '18:00'])
  
  -- 관련 엔티티 참조
  related_entity_type TEXT,  -- 'todo' | 'page_progress' | 'review_request' 등
  related_entity_id UUID,
  
  -- 상태
  is_active BOOLEAN DEFAULT TRUE,
  last_sent_at TIMESTAMPTZ,  -- 마지막 발송 시각
  next_send_at TIMESTAMPTZ,  -- 다음 발송 예정 시각
  
  -- 완료 정보
  completed_at TIMESTAMPTZ,  -- 목표 완료 시각 (리마인드 중지)
  
  -- 메타데이터
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_reminders_user (user_id, is_active, next_send_at),
  INDEX idx_reminders_company (company_id, reminder_type),
  INDEX idx_reminders_target_date (target_date, is_active),
  INDEX idx_reminders_next_send (next_send_at, is_active),
  
  CONSTRAINT chk_reminder_type CHECK (
    reminder_type IN ('deadline', 'task', 'review', 'approval', 'custom')
  )
);
```

**리마인드 예시**:
- 마감일 7일 전, 3일 전, 1일 전 알림 (`reminder_days_before = [7, 3, 1]`)
- 매일 오전 9시, 오후 6시 알림 (`reminder_times = ['09:00', '18:00']`)
- 작업 완료 시 자동 중지 (`completed_at` 설정 시 `is_active = FALSE`)

**리마인드 스케줄링 프로세스**:
```
[사용자] 마감일 설정 또는 작업 생성
  ↓
[시스템] reminder_schedules 생성
  - target_date: 마감일
  - reminder_days_before: [7, 3, 1] (7일 전, 3일 전, 1일 전)
  - reminder_times: ['09:00'] (오전 9시)
  - next_send_at: target_date - 7일 + 09:00 계산
  ↓
[스케줄러] 매일 실행
  - next_send_at이 현재 시각 이하인 항목 조회
  - 알림 발송 (notifications 테이블에 생성)
  - 다음 알림 시각 계산 (target_date - 3일 + 09:00)
  - next_send_at 업데이트
  ↓
[목표 완료] completed_at 설정
  - is_active = FALSE로 변경
  - 리마인드 중지
```

**리마인드 타입별 설명**:
- `deadline`: 마감일 리마인드 (보고서 마감일 등)
- `task`: 작업 리마인드 (할 일 완료 등)
- `review`: 검토 리마인드 (검토 요청 대기 등)
- `approval`: 승인 리마인드 (승인 대기 등)
- `custom`: 사용자 정의 리마인드

---

#### `workflow_approvals` - 통합 승인 워크플로우

**역할**: 다양한 엔티티에 대한 통합 승인 워크플로우 관리

**통합 배경**:
- 기존 `ghg_approval_workflows`, `ghg_approval_steps`, `ghg_unlock_requests` 테이블을 통합하여 모든 승인 워크플로우를 하나의 테이블로 관리
- GHG 전용이 아닌 범용 승인 워크플로우 시스템으로 확장
- 다단계 승인 지원 및 Polymorphic Association으로 다양한 엔티티 타입 지원
- 잠금 해제 요청도 승인 워크플로우의 일종으로 통합

**주요 필드**:
```sql
CREATE TABLE workflow_approvals (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 워크플로우 정보
  workflow_type TEXT NOT NULL,  
  -- 'ghg_unlock' | 'ghg_data_submission' | 'ghg_final_approval' | 
  -- 'data_approval' | 'report_approval' | 'unlock_request' | 'final_submission' | 'custom'
  workflow_category TEXT,  -- 'ghg' | 'sr' | 'general' (선택적, 필터링용)
  workflow_name TEXT NOT NULL,  -- 워크플로우 이름
  
  -- 관련 엔티티 참조 (Polymorphic Association)
  related_entity_type TEXT NOT NULL,  
  -- 'ghg_calculation_snapshots' | 'ghg_emission_results' | 
  -- 'environmental_data' | 'sr_report_content' 등
  -- ⚠️ 'ghg_unlock_request'는 더 이상 사용하지 않음 (workflow_type = 'ghg_unlock'로 처리)
  related_entity_id UUID NOT NULL,
  
  -- 진행 상태
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'approved' | 'rejected' | 'cancelled'
  current_step INTEGER DEFAULT 1,  -- 현재 단계 (1, 2, 3...)
  total_steps INTEGER DEFAULT 1,  -- 총 단계 수
  
  -- 요청자 정보
  requested_by UUID NOT NULL REFERENCES users(id),  -- 요청자
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  request_message TEXT,  -- 요청 메시지
  
  -- 승인자 정보 (JSONB로 유연하게 저장)
  approvers JSONB NOT NULL,  -- [{"user_id": "uuid", "step": 1, "role": "reviewer"}, ...]
  -- 예시: [{"user_id": "uuid-1", "step": 1, "role": "reviewer", "status": "pending"}, {"user_id": "uuid-2", "step": 2, "role": "approver", "status": "pending"}]
  
  -- 완료 정보
  completed_at TIMESTAMPTZ,
  completed_by UUID REFERENCES users(id),
  completion_message TEXT,
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_workflow_company (company_id, status),
  INDEX idx_workflow_entity (related_entity_type, related_entity_id),
  INDEX idx_workflow_category (workflow_category, status),
  INDEX idx_workflow_requested_by (requested_by, status),
  INDEX idx_workflow_status (company_id, status, created_at),
  
  CONSTRAINT chk_workflow_type CHECK (
    workflow_type IN ('ghg_unlock', 'ghg_data_submission', 'ghg_final_approval', 
                     'data_approval', 'report_approval', 'unlock_request', 
                     'final_submission', 'custom')
  ),
  CONSTRAINT chk_workflow_status CHECK (
    status IN ('pending', 'in_progress', 'approved', 'rejected', 'cancelled')
  )
);
```

**기존 테이블과의 매핑**:
- `ghg_approval_workflows.workflow_type = 'unlock'` → `workflow_approvals.workflow_type = 'ghg_unlock'`
- `ghg_approval_workflows.workflow_type = 'data_submission'` → `workflow_approvals.workflow_type = 'ghg_data_submission'`
- `ghg_approval_workflows.workflow_type = 'final_approval'` → `workflow_approvals.workflow_type = 'ghg_final_approval'`
- `ghg_unlock_requests` → `workflow_approvals.workflow_type = 'ghg_unlock'`, `related_entity_type = 'ghg_calculation_snapshots'`

**마이그레이션 전략**:
```sql
-- 기존 ghg_approval_workflows 데이터를 workflow_approvals로 마이그레이션
INSERT INTO workflow_approvals (
  company_id,
  workflow_type,  -- 'ghg_unlock' | 'ghg_data_submission' | 'ghg_final_approval'
  workflow_category,  -- 'ghg'
  related_entity_type,  -- 'ghg_unlock_request' | 'ghg_emission_results' | 'ghg_calculation_snapshots'
  related_entity_id,  -- target_id
  requested_by,
  status,
  current_step,
  total_steps,
  approvers  -- JSONB로 변환: [{"user_id": approver_1_id, "step": 1}, ...]
)
SELECT 
  company_id,
  CASE workflow_type
    WHEN 'unlock' THEN 'ghg_unlock'
    WHEN 'data_submission' THEN 'ghg_data_submission'
    WHEN 'final_approval' THEN 'ghg_final_approval'
  END AS workflow_type,
  'ghg' AS workflow_category,
  CASE workflow_type
    WHEN 'unlock' THEN 'ghg_unlock_request'
    WHEN 'data_submission' THEN 'ghg_emission_results'
    WHEN 'final_approval' THEN 'ghg_calculation_snapshots'
  END AS related_entity_type,
  target_id AS related_entity_id,
  -- requested_by는 기존 테이블에 없으므로 NULL 또는 기본값
  status,
  current_step,
  total_steps,
  jsonb_build_array(
    CASE WHEN approver_1_id IS NOT NULL 
      THEN jsonb_build_object('user_id', approver_1_id, 'step', 1, 'role', 'reviewer', 'status', 'pending')
      ELSE NULL
    END,
    CASE WHEN approver_2_id IS NOT NULL 
      THEN jsonb_build_object('user_id', approver_2_id, 'step', 2, 'role', 'approver', 'status', 'pending')
      ELSE NULL
    END
  ) AS approvers
FROM ghg_approval_workflows;

-- 기존 ghg_unlock_requests 데이터를 workflow_approvals로 마이그레이션
INSERT INTO workflow_approvals (
  company_id,
  workflow_type,  -- 'ghg_unlock'
  workflow_category,  -- 'ghg'
  workflow_name,  -- 'GHG 잠금 해제 요청'
  related_entity_type,  -- 'ghg_calculation_snapshots'
  related_entity_id,  -- period_lock_id에서 변환 (실제 스냅샷 ID)
  requested_by,
  request_message,  -- reason
  status,  -- pending → pending, approved → approved, rejected → rejected
  total_steps,  -- 1 (단일 승인자)
  approvers,  -- JSONB로 변환
  completed_at,  -- approved_at
  completed_by,  -- approved_by
  completion_message  -- approval_comment
)
SELECT 
  ur.company_id,
  'ghg_unlock' AS workflow_type,
  'ghg' AS workflow_category,
  'GHG 잠금 해제 요청' AS workflow_name,
  'ghg_calculation_snapshots' AS related_entity_type,
  -- period_lock_id에서 실제 스냅샷 ID로 변환
  (SELECT id FROM ghg_calculation_snapshots 
   WHERE company_id = ur.company_id 
   AND period_year = pl.period_year 
   AND period_month = pl.period_month 
   AND is_locked = TRUE
   ORDER BY locked_at DESC
   LIMIT 1) AS related_entity_id,
  ur.requested_by::UUID,  -- TEXT → UUID 변환
  ur.reason AS request_message,
  CASE ur.status
    WHEN 'pending' THEN 'pending'
    WHEN 'approved' THEN 'approved'
    WHEN 'rejected' THEN 'rejected'
  END AS status,
  1 AS total_steps,  -- 단일 승인자
  jsonb_build_array(
    CASE WHEN ur.approved_by IS NOT NULL
      THEN jsonb_build_object(
        'user_id', ur.approved_by::UUID,
        'step', 1,
        'role', 'approver',
        'status', CASE ur.status
          WHEN 'pending' THEN 'pending'
          WHEN 'approved' THEN 'approved'
          WHEN 'rejected' THEN 'rejected'
        END,
        'action', CASE ur.status
          WHEN 'approved' THEN 'approved'
          WHEN 'rejected' THEN 'rejected'
          ELSE NULL
        END,
        'comment', ur.approval_comment,
        'action_at', ur.approved_at
      )
      ELSE NULL
    END
  ) AS approvers,
  ur.approved_at AS completed_at,
  ur.approved_by::UUID AS completed_by,
  ur.approval_comment AS completion_message
FROM ghg_unlock_requests ur
LEFT JOIN ghg_period_locks pl ON ur.period_lock_id = pl.id;
```

**잠금 해제 요청 사용 예시**:
```sql
-- 잠금 해제 요청 생성
INSERT INTO workflow_approvals (
  company_id,
  workflow_type,  -- 'ghg_unlock'
  workflow_category,  -- 'ghg'
  workflow_name,  -- 'GHG 잠금 해제 요청'
  related_entity_type,  -- 'ghg_calculation_snapshots'
  related_entity_id,  -- 잠금된 스냅샷 ID
  requested_by,
  request_message,  -- '데이터 오류 정정 필요'
  status,  -- 'pending'
  total_steps,  -- 2 (검토자 → 승인자)
  approvers  -- JSONB
) VALUES (
  'company-123',
  'ghg_unlock',
  'ghg',
  'GHG 잠금 해제 요청',
  'ghg_calculation_snapshots',
  'snapshot-456',  -- 잠금된 스냅샷 ID
  'user-789',  -- 요청자
  '데이터 오류 정정 필요',
  'pending',
  2,
  '[
    {"user_id": "reviewer-001", "step": 1, "role": "reviewer", "status": "pending"},
    {"user_id": "approver-001", "step": 2, "role": "approver", "status": "pending"}
  ]'::jsonb
);

-- 승인 완료 시 실제 잠금 해제 처리
UPDATE ghg_calculation_snapshots
SET is_locked = FALSE,
    unlocked_by = 'approver-001',
    unlocked_at = NOW(),
    unlock_reason = '데이터 오류 정정 필요'
WHERE id = 'snapshot-456';
```

**승인자 JSONB 구조 예시**:
```json
[
  {
    "user_id": "uuid-1",
    "step": 1,
    "role": "reviewer",
    "status": "pending",
    "assigned_at": "2025-01-15T09:00:00Z",
    "action": null,
    "action_at": null,
    "comment": null
  },
  {
    "user_id": "uuid-2",
    "step": 2,
    "role": "approver",
    "status": "pending",
    "assigned_at": "2025-01-15T09:00:00Z",
    "action": null,
    "action_at": null,
    "comment": null
  }
]
```

**잠금 해제 요청 워크플로우 프로세스**:
```
[사용자] 마감된 GHG 산정 결과 수정 필요
  ↓
[사용자] "잠금 해제 요청" 버튼 클릭
  ↓
[시스템] workflow_approvals 생성
  - workflow_type: 'ghg_unlock'
  - related_entity_type: 'ghg_calculation_snapshots'
  - related_entity_id: 잠금된 스냅샷 ID
  - status: 'pending'
  ↓
[검토자] 1단계 검토 및 승인
  - workflow_approval_steps (step_order: 1) 업데이트
  - workflow_approvals.current_step: 2
  - workflow_approvals.status: 'in_progress'
  ↓
[승인자] 2단계 최종 승인 (e-Sign 포함)
  - workflow_approval_steps (step_order: 2) 업데이트
  - e_sign_data 저장
  - workflow_approvals.status: 'approved'
  ↓
[시스템] 실제 잠금 해제 처리
  - ghg_calculation_snapshots.is_locked: FALSE
  - ghg_calculation_snapshots.unlocked_by, unlocked_at 저장
  ↓
[사용자] 데이터 수정 가능
```

---

#### `workflow_approval_steps` - 승인 단계별 상세

**역할**: 각 승인 단계의 상세 정보 및 이력

**주요 필드**:
```sql
CREATE TABLE workflow_approval_steps (
  id UUID PRIMARY KEY,
  workflow_id UUID NOT NULL REFERENCES workflow_approvals(id) ON DELETE CASCADE,
  
  -- 단계 정보
  step_order INTEGER NOT NULL,  -- 1, 2, 3...
  approver_id UUID NOT NULL REFERENCES users(id),  -- 승인자
  approver_role TEXT NOT NULL,  -- 'reviewer' | 'approver' | 'final_approver'
  
  -- 승인 정보
  action TEXT,  -- 'approved' | 'rejected' | 'pending'
  comment TEXT,  -- 승인/반려 코멘트
  action_at TIMESTAMPTZ,  -- 처리 시각
  
  -- e-Sign 정보 (선택적)
  e_sign_data JSONB,  -- {signerId, timestamp, hash, certificate}
  
  -- 알림 정보
  notification_sent BOOLEAN DEFAULT FALSE,  -- 알림 발송 여부
  notification_sent_at TIMESTAMPTZ,  -- 알림 발송 시각
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_workflow_steps_workflow (workflow_id, step_order),
  INDEX idx_workflow_steps_approver (approver_id, action),
  INDEX idx_workflow_steps_action (workflow_id, action),
  
  CONSTRAINT chk_step_role CHECK (
    approver_role IN ('reviewer', 'approver', 'final_approver')
  ),
  CONSTRAINT chk_step_action CHECK (
    action IN ('approved', 'rejected', 'pending', 'cancelled')
  )
);
```

---

### 7.3 할 일(To-do) 리스트 테이블

#### `todos` - 할 일 관리

**역할**: 사용자별 할 일 목록 관리

**주요 필드**:
```sql
CREATE TABLE todos (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  user_id UUID NOT NULL REFERENCES users(id),  -- 담당자
  
  -- 할 일 정보
  title TEXT NOT NULL,  -- 할 일 제목
  description TEXT,  -- 상세 설명
  todo_type TEXT NOT NULL,  -- 'data_input' | 'review' | 'approval' | 'correction' | 'submission'
  
  -- 상태
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'completed' | 'cancelled'
  priority TEXT DEFAULT 'normal',  -- 'low' | 'normal' | 'high' | 'urgent'
  
  -- 기한
  due_date DATE,  -- 마감일
  completed_at TIMESTAMPTZ,  -- 완료 시각
  
  -- 관련 엔티티 참조 (Polymorphic Association)
  related_entity_type TEXT,  -- 'page_progress' | 'review_request' | 'ghg_activity_data' | 'sr_report_content'
  related_entity_id UUID,  -- 관련 엔티티의 PK
  
  -- 메타데이터
  created_by UUID REFERENCES users(id),  -- 생성자
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_todos_user (user_id, status, due_date),
  INDEX idx_todos_company (company_id, status),
  INDEX idx_todos_related (related_entity_type, related_entity_id),
  INDEX idx_todos_due_date (user_id, due_date, status),
  
  CONSTRAINT chk_todo_type CHECK (
    todo_type IN ('data_input', 'review', 'approval', 'correction', 'submission', 'other')
  ),
  CONSTRAINT chk_todo_status CHECK (
    status IN ('pending', 'in_progress', 'completed', 'cancelled')
  ),
  CONSTRAINT chk_todo_priority CHECK (
    priority IN ('low', 'normal', 'high', 'urgent')
  )
);
```

**할 일 자동 생성 예시**:
- GHG 산정 데이터 입력 미완료 → `todo_type = 'data_input'`, `related_entity_type = 'ghg_activity_data'`
- 검토 요청 대기 → `todo_type = 'review'`, `related_entity_type = 'review_request'`
- 승인 대기 → `todo_type = 'approval'`, `related_entity_type = 'review_request'`
- 마감일 임박 → `todo_type = 'submission'`, `due_date` 설정

---

### 7.4 팀원 현황 관리 테이블

#### `team_assignments` - 팀원 작업 할당

**역할**: 팀원별 페이지 담당 및 작업 할당 관리

**주요 필드**:
```sql
CREATE TABLE team_assignments (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  user_id UUID NOT NULL REFERENCES users(id),  -- 담당 팀원
  
  -- 할당 정보
  page_type TEXT NOT NULL,  -- 'company_info' | 'ghg' | 'sr' | 'charts'
  assignment_type TEXT NOT NULL,  -- 'primary' | 'secondary' | 'reviewer' | 'approver'
  
  -- 할당 상태
  status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'inactive' | 'completed'
  
  -- 할당 정보
  assigned_by UUID REFERENCES users(id),  -- 할당한 관리자
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  unassigned_at TIMESTAMPTZ,
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_team_assignments_user (user_id, status),
  INDEX idx_team_assignments_company (company_id, page_type),
  INDEX idx_team_assignments_page (company_id, page_type, status),
  
  CONSTRAINT chk_assignment_page_type CHECK (
    page_type IN ('company_info', 'ghg', 'sr', 'charts')
  ),
  CONSTRAINT chk_assignment_type CHECK (
    assignment_type IN ('primary', 'secondary', 'reviewer', 'approver')
  ),
  CONSTRAINT chk_assignment_status CHECK (
    status IN ('active', 'inactive', 'completed')
  ),
  
  UNIQUE(company_id, user_id, page_type, assignment_type)  -- 중복 할당 방지
);
```

**할당 타입 설명**:
- `primary`: 주 담당자 (작업 수행)
- `secondary`: 보조 담당자 (협업)
- `reviewer`: 검토자 (검토만)
- `approver`: 승인자 (최종 승인)

---

#### `team_activity_logs` - 팀원 활동 로그

**역할**: 팀원별 활동 이력 추적 (저장, 제출, 승인 등)

**주요 필드**:
```sql
CREATE TABLE team_activity_logs (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  user_id UUID NOT NULL REFERENCES users(id),  -- 활동한 사용자
  
  -- 활동 정보
  action_type TEXT NOT NULL,  -- 'save' | 'submit' | 'approve' | 'reject' | 'comment' | 'assign' | 'update'
  action_description TEXT NOT NULL,  -- 'GHG 산정 결과 저장' | 'SR 보고서 검토 요청' 등
  page_type TEXT,  -- 'company_info' | 'ghg' | 'sr' | 'charts'
  
  -- 관련 엔티티 참조 (Polymorphic Association)
  related_entity_type TEXT,  -- 'ghg_emission_results' | 'sr_report_content' | 'review_request' 등
  related_entity_id UUID,
  
  -- 변경 내용 (선택적)
  change_summary JSONB,  -- 변경된 필드 요약
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_activity_company (company_id, created_at),
  INDEX idx_activity_user (user_id, created_at),
  INDEX idx_activity_page (company_id, page_type, created_at),
  INDEX idx_activity_type (company_id, action_type, created_at),
  
  CONSTRAINT chk_action_type CHECK (
    action_type IN ('save', 'submit', 'approve', 'reject', 'comment', 'assign', 'update', 'delete', 'export')
  )
);
```

---

### 7.5 리포트 출력 테이블

#### `report_exports` - 리포트 출력 이력

**역할**: 리포트 다운로드/출력 이력 관리

**주요 필드**:
```sql
CREATE TABLE report_exports (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  user_id UUID NOT NULL REFERENCES users(id),  -- 다운로드한 사용자
  
  -- 리포트 정보
  report_type TEXT NOT NULL,  -- 'excel' | 'powerpoint' | 'pdf' | 'word'
  report_name TEXT NOT NULL,  -- 리포트 파일명
  report_version TEXT,  -- 'v1' | 'v2' 등
  
  -- 파일 정보
  file_path TEXT NOT NULL,  -- 저장된 파일 경로
  file_size BIGINT,  -- 파일 크기 (bytes)
  file_hash TEXT,  -- 파일 해시 (무결성 검증용)
  
  -- 리포트 내용 스냅샷 (선택적)
  report_snapshot JSONB,  -- 리포트 생성 시점의 데이터 스냅샷
  
  -- 승인 정보
  approved_at TIMESTAMPTZ,  -- 최종 승인 시각 (승인된 리포트만 다운로드 가능)
  approved_by UUID REFERENCES users(id),  -- 승인자
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_report_exports_company (company_id, created_at),
  INDEX idx_report_exports_user (user_id, created_at),
  INDEX idx_report_exports_type (company_id, report_type),
  INDEX idx_report_exports_approved (company_id, approved_at),
  
  CONSTRAINT chk_report_type CHECK (
    report_type IN ('excel', 'powerpoint', 'pdf', 'word')
  )
);
```

**다운로드 권한**:
- 최종 승인된 리포트만 다운로드 가능 (`approved_at IS NOT NULL`)
- 팀장과 팀원 모두 다운로드 가능 (승인 후)

---

### 7.6 코멘트 및 질의응답 테이블

#### `comments` - 범용 코멘트 (통합)

**역할**: 모든 엔티티에 대한 범용 코멘트 및 질의응답 관리 (감사 코멘트, 검토 요청, 피드백 통합)

**통합 배경**:
- 기존 `ghg_audit_comments`와 `review_requests` 테이블을 통합하여 모든 코멘트 기능을 하나의 테이블로 관리
- 감사인-실무자 질의응답, 팀원-팀장 검토 요청/피드백, 일반 코멘트 등 모든 코멘트 기능 지원
- 스레드 형태 질의응답 지원 및 Polymorphic Association으로 다양한 엔티티 타입 지원

**주요 필드**:
```sql
CREATE TABLE comments (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 연결 정보 (Polymorphic Association)
  related_entity_type TEXT NOT NULL,  
  -- 'ghg_activity_data' | 'ghg_emission_results' | 'sr_report_content' | 
  -- 'review_request' | 'workflow_approval' | 'page_progress' 등
  related_entity_id UUID NOT NULL,
  
  -- 코멘트 정보
  comment_text TEXT NOT NULL,
  comment_type TEXT NOT NULL,  
  -- 'question' | 'finding' | 'recommendation' | 'feedback' | 'review' | 'general'
  
  -- 작성자 정보
  commented_by UUID NOT NULL REFERENCES users(id),
  commented_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- 스레드 지원
  parent_id UUID REFERENCES comments(id),  -- 부모 코멘트 (스레드)
  thread_id UUID,  -- 스레드 ID (첫 코멘트의 ID, 자기 참조)
  
  -- 상태 관리
  status TEXT DEFAULT 'open',  -- 'open' | 'resolved' | 'closed'
  resolved_by UUID REFERENCES users(id),
  resolved_at TIMESTAMPTZ,
  
  -- 역할 정보
  commenter_role TEXT,  -- 'auditor' | 'practitioner' | 'reviewer' | 'approver' | 'team_member' | 'team_leader'
  
  -- 검토 요청 관련 (기존 review_requests 기능)
  is_review_request BOOLEAN DEFAULT FALSE,  -- 검토 요청 여부
  review_status TEXT,  -- 'pending' | 'approved' | 'rejected' | 'cancelled' (검토 요청인 경우)
  reviewed_by UUID REFERENCES users(id),  -- 검토자 (검토 요청인 경우)
  reviewed_at TIMESTAMPTZ,  -- 검토 시각
  review_duration_seconds INTEGER,  -- 검토 소요 시간 (초)
  
  -- 페이지 정보 (검토 요청인 경우)
  page_type TEXT,  -- 'company_info' | 'ghg' | 'sr' | 'charts'
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_comments_entity (related_entity_type, related_entity_id),
  INDEX idx_comments_user (commented_by, created_at),
  INDEX idx_comments_thread (thread_id, created_at),
  INDEX idx_comments_status (company_id, status),
  INDEX idx_comments_review (company_id, is_review_request, review_status),
  INDEX idx_comments_page (company_id, page_type, review_status),
  
  CONSTRAINT chk_comment_type CHECK (
    comment_type IN ('question', 'finding', 'recommendation', 'feedback', 'review', 'general')
  ),
  CONSTRAINT chk_comment_status CHECK (
    status IN ('open', 'resolved', 'closed')
  ),
  CONSTRAINT chk_review_status CHECK (
    review_status IN ('pending', 'approved', 'rejected', 'cancelled') OR review_status IS NULL
  )
);
```

**사용 시나리오**:

**시나리오 1: 감사인 질의응답**
```sql
-- 감사인이 질문
INSERT INTO comments (
  company_id, related_entity_type, related_entity_id,
  comment_text, comment_type, commented_by, commenter_role,
  thread_id
) VALUES (
  'company-001', 'ghg_emission_results', 'result-123',
  'Scope 1 배출량 산정 근거를 확인하고 싶습니다.',
  'question', 'auditor-001', 'auditor',
  gen_random_uuid()  -- 새 스레드 시작
);

-- 실무자가 답변
INSERT INTO comments (
  company_id, related_entity_type, related_entity_id,
  comment_text, comment_type, commented_by, commenter_role,
  parent_id, thread_id  -- 부모 코멘트 참조
) VALUES (
  'company-001', 'ghg_emission_results', 'result-123',
  '배출계수 EF-LNG-2024를 적용하여 산정했습니다. 증빙 자료는 첨부 파일을 참고해주세요.',
  'general', 'practitioner-001', 'practitioner',
  'comment-uuid-1',  -- 부모 코멘트 ID
  (SELECT thread_id FROM comments WHERE id = 'comment-uuid-1')  -- 같은 스레드
);
```

**시나리오 2: 검토 요청**
```sql
-- 팀원이 검토 요청
INSERT INTO comments (
  company_id, related_entity_type, related_entity_id,
  comment_text, comment_type, commented_by, commenter_role,
  is_review_request, review_status, page_type,
  thread_id
) VALUES (
  'company-001', 'sr_report_content', 'content-456',
  'SR 보고서 검토 부탁드립니다.',
  'review', 'team-member-001', 'team_member',
  TRUE, 'pending', 'sr',
  gen_random_uuid()
);

-- 팀장이 검토 후 승인
UPDATE comments
SET review_status = 'approved',
    reviewed_by = 'team-leader-001',
    reviewed_at = NOW(),
    comment_text = comment_text || E'\n\n[승인] 검토 완료되었습니다.',
    status = 'resolved',
    resolved_by = 'team-leader-001',
    resolved_at = NOW()
WHERE id = 'comment-uuid-2';
```

**시나리오 3: 스레드 형태 질의응답**
```sql
-- 질문 1
INSERT INTO comments (..., thread_id) VALUES (..., 'thread-001');

-- 답변 1
INSERT INTO comments (..., parent_id, thread_id) 
VALUES (..., 'comment-1', 'thread-001');

-- 추가 질문 (같은 스레드)
INSERT INTO comments (..., parent_id, thread_id) 
VALUES (..., 'comment-2', 'thread-001');

-- 답변 2
INSERT INTO comments (..., parent_id, thread_id) 
VALUES (..., 'comment-3', 'thread-001');
```

**기존 테이블과의 매핑**:
- `ghg_audit_comments` → `comments` (comment_type: 'question' | 'finding' | 'recommendation', commenter_role: 'auditor' | 'practitioner')
- `review_requests` → `comments` (is_review_request = TRUE, comment_type: 'review', review_status 사용)

**마이그레이션 전략**:
```sql
-- 1. 기존 ghg_audit_comments 데이터를 comments로 마이그레이션
INSERT INTO comments (
  company_id, related_entity_type, related_entity_id,
  comment_text, comment_type, commented_by, commenter_role,
  commented_at, thread_id
)
SELECT 
  company_id,
  related_entity_type,
  related_entity_id,
  comment_text,
  COALESCE(comment_type, 'general'),
  commented_by::UUID,  -- TEXT → UUID 변환
  CASE 
    WHEN commented_by LIKE '%auditor%' THEN 'auditor'
    ELSE 'practitioner'
  END AS commenter_role,
  commented_at,
  gen_random_uuid() AS thread_id  -- 새 스레드 시작
FROM ghg_audit_comments
WHERE parent_id IS NULL;  -- 첫 코멘트만

-- 응답 코멘트는 parent_id로 연결
INSERT INTO comments (
  company_id, related_entity_type, related_entity_id,
  comment_text, comment_type, commented_by, commenter_role,
  parent_id, thread_id, commented_at
)
SELECT 
  company_id,
  related_entity_type,
  related_entity_id,
  response_text,
  'general',
  responded_by::UUID,
  'practitioner',
  (SELECT id FROM comments WHERE ...),  -- 부모 코멘트 ID
  (SELECT thread_id FROM comments WHERE ...),  -- 같은 스레드
  responded_at
FROM ghg_audit_comments
WHERE response_text IS NOT NULL;

-- 2. 기존 review_requests 데이터를 comments로 마이그레이션
INSERT INTO comments (
  company_id, related_entity_type, related_entity_id,
  comment_text, comment_type, commented_by, commenter_role,
  is_review_request, review_status, reviewed_by, reviewed_at,
  page_type, created_at
)
SELECT 
  company_id,
  COALESCE(related_entity_type, 'page_progress'),
  COALESCE(related_entity_id, gen_random_uuid()),
  COALESCE(request_message, '검토 요청'),
  'review',
  requested_by,
  'team_member',
  TRUE,
  request_status,
  reviewed_by,
  reviewed_at,
  page_type,
  created_at
FROM review_requests;
```

---

#### `review_requests` - 검토 요청 (레거시)

**역할**: 팀원의 검토 요청 및 팀장의 승인/반려 관리

**⚠️ 통합 계획**: 이 테이블은 `comments` 범용 코멘트 테이블로 통합 예정입니다.  
새로운 검토 요청 기능은 `comments` 테이블을 사용하시기 바랍니다 (`is_review_request = TRUE`).

**주요 필드**:
```sql
CREATE TABLE review_requests (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 요청 정보
  page_type TEXT NOT NULL,  -- 'company_info' | 'ghg' | 'sr' | 'charts'
  requested_by UUID NOT NULL REFERENCES users(id),  -- 요청자 (팀원)
  reviewed_by UUID REFERENCES users(id),  -- 처리자 (팀장)
  
  -- 요청 내용
  request_message TEXT,  -- 요청 메시지
  request_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected' | 'cancelled'
  
  -- 피드백 내용
  feedback_message TEXT,  -- 팀장 피드백
  feedback_type TEXT,  -- 'approval' | 'rejection' | 'revision_request'
  
  -- 처리 정보
  reviewed_at TIMESTAMPTZ,  -- 처리 시각
  review_duration_seconds INTEGER,  -- 처리 소요 시간 (초)
  
  -- 관련 엔티티 참조
  related_entity_type TEXT,  -- 'ghg_emission_results' | 'sr_report_content' 등
  related_entity_id UUID,
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_review_requests_company (company_id, request_status),
  INDEX idx_review_requests_requested_by (requested_by, request_status),
  INDEX idx_review_requests_reviewed_by (reviewed_by, request_status),
  INDEX idx_review_requests_page (company_id, page_type, request_status),
  
  CONSTRAINT chk_review_page_type CHECK (
    page_type IN ('company_info', 'ghg', 'sr', 'charts')
  ),
  CONSTRAINT chk_review_status CHECK (
    request_status IN ('pending', 'approved', 'rejected', 'cancelled')
  )
);
```

---

## 8. 온프레미스 로그인 및 사용자 관리 테이블

### 8.1 사용자 테이블 (온프레미스용)

#### `users` - 사용자 정보

**역할**: 온프레미스 환경의 사용자 정보 및 권한 관리

**주요 필드**:
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- ===== 기본 정보 =====
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,  -- 암호화된 비밀번호 (bcrypt 등)
  name TEXT,
  
  -- ===== 권한 정보 (관리자가 미리 설정) =====
  role TEXT NOT NULL,  -- 'final_approver' | 'esg_team' | 'dept_user' | 'viewer'
  department TEXT,  -- '환경안전팀' | '인사팀' | '재무팀' | 'ESG팀'
  position TEXT,  -- '팀장' | '팀원' | '대표이사'
  
  -- ===== 계정 상태 =====
  is_active BOOLEAN DEFAULT TRUE,  -- 활성화 여부
  is_first_login BOOLEAN DEFAULT TRUE,  -- 최초 로그인 여부 (비밀번호 변경 필요)
  password_changed_at TIMESTAMPTZ,  -- 비밀번호 변경 시각
  last_login_at TIMESTAMPTZ,  -- 마지막 로그인 시각
  
  -- ===== 초기 비밀번호 정보 =====
  initial_password TEXT,  -- 초기 비밀번호 (평문, 최초 로그인 후 삭제)
  must_change_password BOOLEAN DEFAULT TRUE,  -- 비밀번호 변경 필수 여부
  
  -- ===== 메타데이터 =====
  created_by UUID REFERENCES users(id),  -- 등록한 관리자
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_users_company (company_id),
  INDEX idx_users_email (email),
  INDEX idx_users_active (company_id, is_active),
  INDEX idx_users_role (company_id, role),
  
  CONSTRAINT chk_user_role CHECK (
    role IN ('final_approver', 'esg_team', 'dept_user', 'viewer')
  )
);
```

**권한 계층 구조**:
- `final_approver`: 최종 승인권자 (최고 권한)
- `esg_team`: ESG팀 (관리 권한)
- `dept_user`: 현업팀 (작업 권한)
- `viewer`: 일반 사용자 (조회 권한)

---

#### `companies` - 회사 정보

**역할**: 회사 기본 정보 및 마감일 관리

**주요 필드**:
```sql
CREATE TABLE companies (
  id UUID PRIMARY KEY,
  
  -- ===== 기본 정보 =====
  company_name_ko TEXT NOT NULL,
  company_name_en TEXT,
  business_registration_number TEXT UNIQUE,
  representative_name TEXT,
  industry TEXT,
  
  -- ===== 연락처 =====
  address TEXT,
  phone TEXT,
  email TEXT,
  website TEXT,
  
  -- ===== 마감일 관리 =====
  report_deadline DATE,  -- 보고서 마감일 (팀장 설정)
  deadline_set_by UUID REFERENCES users(id),  -- 마감일 설정한 사용자
  deadline_set_at TIMESTAMPTZ,  -- 마감일 설정 시각
  
  -- ===== 최종 승인 정보 =====
  final_approved_at TIMESTAMPTZ,  -- 최종 보고서 승인 시각
  final_approved_by UUID REFERENCES users(id),  -- 최종 승인자
  
  -- ===== 메타데이터 =====
  created_by UUID REFERENCES users(id),  -- 등록한 관리자
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_companies_deadline (report_deadline),
  INDEX idx_companies_approved (final_approved_at)
);
```

---

#### `user_sessions` - 사용자 세션 관리

**역할**: 로그인 세션 및 JWT 토큰 관리

**주요 필드**:
```sql
CREATE TABLE user_sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id),
  
  -- 세션 정보
  session_token TEXT NOT NULL UNIQUE,  -- JWT 토큰 또는 세션 토큰
  refresh_token TEXT,  -- 리프레시 토큰 (선택적)
  
  -- 세션 상태
  is_active BOOLEAN DEFAULT TRUE,  -- 활성 세션 여부
  expires_at TIMESTAMPTZ NOT NULL,  -- 세션 만료 시각
  
  -- 접속 정보
  ip_address TEXT,  -- 접속 IP
  user_agent TEXT,  -- 브라우저 정보
  device_type TEXT,  -- 'desktop' | 'mobile' | 'tablet'
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_sessions_user (user_id, is_active),
  INDEX idx_sessions_token (session_token),
  INDEX idx_sessions_expires (expires_at),
  INDEX idx_sessions_company (company_id, is_active)
);
```

**세션 관리**:
- 로그인 시 세션 생성
- 로그아웃 시 `is_active = FALSE` 설정
- 만료된 세션 자동 정리 (배치 작업)

---

#### `password_reset_tokens` - 비밀번호 재설정 토큰

**역할**: 비밀번호 재설정을 위한 임시 토큰 관리

**주요 필드**:
```sql
CREATE TABLE password_reset_tokens (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  
  -- 토큰 정보
  reset_token TEXT NOT NULL UNIQUE,  -- 재설정 토큰
  expires_at TIMESTAMPTZ NOT NULL,  -- 토큰 만료 시각
  
  -- 사용 정보
  is_used BOOLEAN DEFAULT FALSE,  -- 사용 여부
  used_at TIMESTAMPTZ,  -- 사용 시각
  
  -- 메타데이터
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_reset_tokens_user (user_id, is_used),
  INDEX idx_reset_tokens_token (reset_token),
  INDEX idx_reset_tokens_expires (expires_at)
);
```

---

## 참조 문서

- **테이블 정의**: 이 문서가 모든 테이블 DDL의 단일 참조입니다. 아래 문서는 프로세스·아키텍처 상세용입니다.
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 시스템 아키텍처
- [DATA_COLLECTION.md](./DATA_COLLECTION.md) - 데이터 수집 전략
- [DATA_ONTOLOGY.md](./DATA_ONTOLOGY.md) - 데이터 온톨로지 (통합 컬럼 매핑 설계 상세)
- [HISTORICAL_REPORT_PARSING.md](./HISTORICAL_REPORT_PARSING.md) - 전년도 SR 보고서 파싱 파서 설계
- [SR_REPORT_BENCHMARKING.md](./SR_REPORT_BENCHMARKING.md) - SR 보고서 벤치마킹·평가 플로우
- [USER_JOURNEY_MAP.md](./USER_JOURNEY_MAP.md) - 사용자 저니맵
- [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) - 구현 가이드
- [AUTHENTICATION_ONPREMISE.md](./AUTHENTICATION_ONPREMISE.md) - 온프레미스 인증·사용자 관리
- [JOURNEYMAP_LOGIN_ONPREMISE.md](../../www.ifrsseed.com/md_files/01_journey_map/JOURNEYMAP_LOGIN_ONPREMISE.md) - 온프레미스 로그인 저니맵
