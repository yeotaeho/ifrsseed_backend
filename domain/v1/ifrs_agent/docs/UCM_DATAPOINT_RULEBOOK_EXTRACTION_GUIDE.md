# UCM용 Data Point·Rulebook 추출 가이드

## 1. 목적과 범위

이 문서는 **기준서(예: GRI, IFRS, ESRS 등) 원문**에서 `data_point.json`·`rulebook.json` 형태의 데이터를 추출할 때의 **기준·조건·품질 기준**을 정의합니다. 목표는 다음 파이프라인에 적합한 온톨로지 시드를 만드는 것입니다.

- **UnifiedColumnMapping(UCM)** 테이블 값 채우기 (`mapped_dp_ids`, 통합 컬럼 메타 등)
- **임베딩 기반 매핑** (보고서 문단·표·지표 → 후보 DP/Rulebook 검색)
- **LLM 검증** (수용/검토/거절, 누락·모순 탐지, 교차 참조 설명)

상위 설계는 [DATA_ONTOLOGY.md](./DATA_ONTOLOGY.md)의 **Data Point**, **rulebooks** 테이블 역할, 임베딩 생성 원칙을 전제로 합니다.

---

## 2. 용어 정리

| 용어 | 의미 |
|------|------|
| **요구사항(Requirement)** | “조직은 … 해야 한다”처럼 **보고 의무**를 규정하는 문장(공개 번호, 항목 a–j 등). |
| **지침(Guidance)** | 요구사항을 **해석·보완**하는 설명, 예시, 교차 참조, 계산식. |
| **최소 공시 단위(DP)** | 보고서 한 덩어리로 **독립 검증·매핑** 가능한 최소 정보 단위. |
| **Rulebook** | 특정 DP(또는 공개 묶음)에 붙는 **규범 텍스트 + 구조화된 검증 힌트**. |

---

## 3. Data Point 추출 기준

### 3.1 언제 하나의 DP로 쪼갤 것인가 (분해 규칙)

다음 중 **하나라도** 해당하면 별도 `dp_id`를 두는 것이 UCM·임베딩·LLM 검증에 유리합니다.

1. **별도 검증 가능성**: 보고서에서 “있음/없음”, “수치/비율”, “예/아니오”로 **독립적으로 채점**할 수 있는가.
2. **별도 임베딩 의미**: 검색 쿼리(예: “CapEx/OpEx 구분”, “1.5°C 시나리오”)가 **한 덩어리에만** 걸리는가.
3. **기준서 구조**: 공개 **하위 항목**(예: 102-1-a … 102-1-j, 요구문에 열거된 **i·ii·iii**), **조건부 공시**(“계획이 없으면 …”)가 명시되어 있는가.
4. **데이터 타입이 달라지는가**: 서술(`narrative`) vs 수치(`quantitative`) vs 이분(`binary`)이 섞이면 **분리**한다.

**반대로**, 아래는 한 DP에 묶는 편이 좋다.

- 단순히 **같은 주제의 배경 설명**이 이어지고, 검증 포인트가 하나뿐인 경우.
- 상위 공개가 **목차/개요**이고 하위에 실질 요구가 모두 있는 경우 → 상위는 **요약 DP**, 하위는 **실무 DP**로 이원화.

### 3.2 DP 식별자·코딩 규칙 (조건)

**이 저장소(ifrs_agent `gri_102` 시드)의 표준 명명**은 아래와 같다. 문서·코드·JSON이 모두 이 패턴을 따른다.

| 구분 | 패턴 | 예시 |
|------|------|------|
| 최상위 기준 | `GRI102` | GRI 102: 기후 변화 |
| 섹션 | `GRI102-SEC-{n}` | `GRI102-SEC-1` (주제별 관리), `GRI102-SEC-2` (주제별 공개) |
| 공개 본문 | `GRI102-{공개번호}` | `GRI102-1` (= 공개 102-1), `GRI102-2`, `GRI102-3` |
| 하위 항목 | 하이픈 연결 | `GRI102-1-c`, `GRI102-2-b-iii`, `GRI102-3-a-i` |

| 조건 | 권장 |
|------|------|
| `dp_id` | 위 표준에 맞는 **안정적 ID**. 공개 번호가 102-1이면 접두는 `GRI102-1`이지, `GRI102-102-1`처럼 `102`를 이중으로 넣지 않는다. 리비전 시에도 **동일 의미면 ID 유지**, 의미 변경 시 버전 필드나 별도 매핑 테이블로 관리. |
| `dp_code` | 기계 친화적 상수명. 공개 번호는 `DIS_1`, `DIS_2` 형태로 표기 (`GRI_102_DIS_1_C_EXPENDITURE`). |
| `parent_indicator` / `child_dps` | 기준서 계층과 **동일 방향**. UCM은 여러 DP를 묶을 수 있으므로 **트리 일관성**이 깨지지 않게 유지. |

### 3.2.1 원천(제공 데이터)에 맞춘 `dp_id`만 — 임의 접미어·가상 항목 금지

**이번 저장소 시드 작업의 강제 원칙:** 추출에 사용한 **기준서/제공 텍스트**에 **명시된 공개·하위 항목**(문자 `a`–`k`, 로마숫자 `i`·`ii` 등)에만 `dp_id`를 부여한다.

- **금지:** 원문 **요구사항** 목록에 없는 문자·번호를 붙여 `GRI102-4-l`, `GRI102-4-i-pct`처럼 **임의로 새 `dp_id`를 만드는 것**. (지침 제목이 요구 항목과 번호가 겹쳐 보여도, **요구 항목에 해당 글자가 없으면** 별도 DP로 쪼개지 않는다.)
- **로마숫자 하위 항목(`i`, `ii`, `iii`, …) — 요구사항에 열거된 경우:** 기준서 **요구사항** 본문에서 한 문자 항목(예: `a`, `c`, `b`) 아래에 `i.`, `ii.`, `iii.` 형태로 **독립 문항**이 나열되면, 각 로마숫자는 **별도의 최소 공시 단위**로 취급한다. `dp_id`는 원문과 동일하게 `…-{letter}-i`, `…-{letter}-ii` … 로 부여한다(예: `GRI2-4-a-i`, `GRI2-4-a-ii`). 필요 시 그룹용으로 상위 `…-{letter}` 요약 DP(자식을 `i`·`ii`…)를 둘 수 있다. (재진술 **사유** vs **영향**처럼 검색·검증 질문이 갈리는 경우가 대표적이다.)
- **로마숫자가 없거나 지침에만 있는 경우:** 같은 문장·항목 안에 여러 검증 포인트(CO₂e·기준연도 대비 %·식 등)가 있어도 **요구사항이 로마숫자로 쪼개져 있지 않으면** **한 `dp_id`**에 두고, 세부는 `validation_rules`·`description`·**지침 전용 rulebook**(`section_type`: `guidance`)에만 기술한다.
- **지침 전용 블록**(예: PDF 절명이 「102-4-k 지침」이나 본문에 **요구 `l` 항목이 없음**): **`rulebook_id` + `related_dp_ids`**로만 추적하고, `primary_dp_id`는 해당 공개 루트(예: `GRI102-4`) 또는 원문과 직접 대응하는 **기존** 하위 DP 중 가장 근접한 것을 택한다. **새 `dp_id`를 “지침용”으로 발급하지 않는다.**

3.1의 “분해 규칙”과 충돌할 때는 **항상 3.2.1을 우선**한다. (검색·검증 편의만으로 원문에 없는 하위 DP를 추가하지 않는다.)

**`rulebook_id` (프로젝트 관례)**

- 표준·섹션: `RULE_GRI102`, `RULE_GRI102_SEC_1`, `RULE_GRI102_SEC_2`
- 공개 요구사항 묶음: `RULE_GRI102_1` (= 공개 102-1)
- 지침·세부: `RULE_GRI102_1_C`, `RULE_GRI102_3_INTRO` 등 — `primary_dp_id`는 대응하는 `dp_id`와 맞출 것.

### 3.3 임베딩 매핑에 필요한 필드 품질

[DATA_ONTOLOGY.md](./DATA_ONTOLOGY.md)에 따르면 DP 임베딩 텍스트는 `name_ko`, `name_en`, `description`, `topic`, `subtopic`, `standard`, `category`, `dp_type`, `unit`, `validation_rules`, `value_range`, `disclosure_requirement`, `reporting_frequency`, `financial_linkages` 등을 포함할 수 있습니다.

**품질 조건:**

- **`description`**: 원문을 베끼기보다, **무엇을 보고해야 하는지**를 2~4문장으로 요약. 동의어·영문 약어·측정 대상을 넣어 검색 적합도를 높인다.
- **`name_ko` / `name_en`**: 검색에 자주 쓰일 **짧은 레이블** + 공식 명칭(공개 번호) 병기.
- **`topic` / `subtopic`**: 필터링용. 너무 넓지 않게 (예: subtopic에 “전환 계획 지출”처럼 **구체화**).
- **`dp_type` / `unit`**: 수치형이면 **단위 필수** (`currency_krw`, `percentage`, `tco2e` 등). 서술형이면 `unit: null`.
- **`validation_rules`**: 문자열 배열 또는 구조화 객체(프로젝트 관례에 따름). **규칙 엔진·LLM이 동일하게 해석**할 수 있게 **한 줄에 한 검증 의도**를 쓴다. (예: “CapEx/OpEx 구분 보고”, “감사 재무제표와 대조”)

### 3.3.1 `equivalent_dps` 사용 시 유의

- **가능하면** DB·온톨로지에 실제로 존재하는 다른 `dp_id`만 넣는다.
- 아직 시드에 없는 표준 라벨(`IFRS-S2`, `TCFD-*` 등)을 넣는 경우, 향후 **실제 DP로 치환**하거나 별도 매핑 테이블로 정리할 계획을 둔다. (임베딩/검색에는 도움이 될 수 있으나 UCM `mapped_dp_ids` 무결성 검사와는 별개)

### 3.3.2 금액·비율·복합 지표를 한 DP에 둘 때

- 원문 **요구사항**이 **로마숫자 `i`·`ii`…** 또는 동급의 **명시적 하위 라벨**로 금액·비율·기타 항목을 나눈 경우에는 §3.2.1에 따라 **항목별 `dp_id`**를 둔다.
- 원문이 **한 항목 문장**에 금액·비율·식을 함께 요구하고 **로마숫자 등으로 쪼개져 있지 않으면**(§3.2.1), **하나의 `dp_id`**에 두고 `validation_rules`·지침 rulebook에 세부를 둔다. `-pct`, `-amount` 등 **원문에 없는 접미어로 DP를 쪼개지 않는다.**
- §7 예시 A의 “비율이 필요하면 하위 DP 분리 검토”는 **원문 요구사항에 해당 하위 라벨(로마숫자 등)이 있을 때만** 적용한다.

### 3.4 UCM·재무 연계를 위한 선택 필드

UCM의 `financial_linkages`, `financial_impact_type` 생성 시 참고되므로, 다음이 있으면 DP에 명시한다.

- 명시적 **지출·자산·부채·손익** 연관이 있는 공시 (예: 전환 지출, 배출권, 좌초자산).
- **영향 방향**이 뚜렷할 때만 `financial_impact_type`을 채운다 (`positive` / `negative` / `neutral`). 애매하면 비우고 rulebook에서 서술.

### 3.5 `disclosure_requirement`·`reporting_frequency`

- 기준서가 **필수/권장/조건부**를 구분하면 그에 맞춘다.
- **조건부**(예: “전환 계획이 없으면 j 항목”)는 **반드시** DP `description`과 `validation_rules`에 **조건을 문장으로** 남긴다. Rulebook의 `required_actions`에만 `condition`을 두고 DP 쪽이 비어 있으면, LLM이 DP만 보고 판단할 때 누락되기 쉽다. (코드화 키를 쓸 경우 프로젝트 전체 enum과 일치시킬 것)

---

## 4. Rulebook 추출 기준

Rulebook은 “긴 원문 저장소”가 아니라 **DP에 대한 규범 레이어**다. 한 레코드는 보통 다음을 만족시킨다.

### 4.1 Rulebook을 나누는 기준

| 분리 단위 | 설명 |
|-----------|------|
| **공개 단위** | 예: `102-1` 전체 요구사항을 하나의 `RULE_GRI102_1`로 두고, 하위는 별도 rulebook 또는 동일 레코드의 섹션으로 관리(프로젝트 관례 선택). |
| **지침 단위** | “102-1-c에 대한 지침”처럼 **원문에 제목이 있는 블록**은 별도 `rulebook_id`로 두면 임베딩 정확도가 오른다. |
| **검증 패킷** | 동일 지침 안에서도 `required_actions` / `verification_checks`가 과도하게 많으면 **주제별**(재무, 시나리오, 이해관계자)로 쪼개는 것을 검토한다. |

### 4.2 필수 연결 조건

- **`primary_dp_id`**: 이 rulebook이 **가장 직접적으로 뒷받침하는 DP** 하나. 모호하면 “가장 좁은 하위 DP”를 택한다. **지침만 있고 대응 요구 항목 문자가 없으면**(§3.2.1) 가상 하위 `dp_id`를 만들지 말고, 해당 공개 **상위 DP**(예: `GRI102-4`) 또는 원문과 직접 매핑되는 기존 항목을 `primary_dp_id`로 둔다.
- **`related_dp_ids`**: 교차 참조·대체 공시 가능(“GRI 2-23에 썼으면 참조”) 등 **다른 DP와의 관계**를 배열로 유지.
- **`section_content`**: 원문 의미 손실을 줄이되, **중복이 심한 머리말**은 요약해도 된다. 임베딩에는 `key_terms`, `related_concepts`가 보완 역할을 한다.

### 4.3 `validation_rules` 구조화 (LLM·룰 검증 공통)

프로젝트 JSON 예시에 맞추되, 다음 **최소 패턴**을 권장한다.

- **`section_type`**: `disclosure_requirement` | `guidance` | `standard_introduction` 등 — 라우팅용.
- **`key_terms` / `related_concepts`**: 임베딩·키워드 룰용. **다국어 혼용 시** 검색 언어를 고려해 영문 표준 용어를 일부 포함한다.
- **`required_actions`**: `{ "action", "description", "mandatory": true/false, "condition": "..." }`  
  - LLM은 `description`을 프롬프트 근거로 사용한다.
  - 조건부 항목은 반드시 `condition`을 채운다.
- **`verification_checks`**: `{ "check_id", "description", "expected" }` — 자동/반자동 검증·평가 루프의 **단위 테스트** 역할.
  - **권장:** 지침 rulebook에도 가능하면 **최소 1개 이상** 두어, 자동화·회귀 검증에 쓸 수 있게 한다.
  - **허용:** 초안 단계에서 빈 배열 `[]`을 두었더라도, 머지 전에 보완하는 것을 원칙으로 한다. 동일 `check_id`는 파일·전역에서 **중복하지 않는다** (§8).
- **`cross_references`**: `validation_rules` 객체 **내부**에 둔다 (프로젝트 JSON 관례). 다른 공개·외부 문헌·내부 DP 참조. “참조로 대체 가능” 같은 **정책 정보**를 넣으면 LLM이 누락 오탐을 줄인다.

---

## 5. UCM 적합성을 위한 통합 품질 조건

UCM 한 행은 보통 **여러 DP**를 묶는다. 시드 데이터 단계에서 다음을 만족할수록 이후 자동 매핑 품질이 좋다.

1. **동일 공개 묶음의 DP**끼리 `child_dps` / `parent_indicator`가 일관된다.
2. **서로 다른 공개**를 한 DP `description`에 합쳐 쓰지 않는다 (임베딩 혼선).
3. **정량 DP**는 `unit`·`value_range`가 있어 Supervisor 검증이 가능하다.
4. **Rulebook의 `verification_checks`**가 DP `validation_rules`와 **서로 모순**되지 않는다.
5. **교차 참조**는 rulebook에 두고, DP에는 “어디를 보라”는 한 줄 요약만 넣어도 된다.

---

## 6. 추출 워크플로우 (권장)

1. **원문 구조화**: 공개 번호·항목·지침 블록 경계를 표시한다.
2. **DP 후보 목록**: 항목별로 3.1 규칙을 적용해 분해/병합한다.
3. **Rulebook 후보**: 요구사항 블록 vs 지침 블록을 분리한다.
4. **검증 정합성**: 각 `verification_check`가 특정 DP에 매핑 가능한지 확인한다.
5. **임베딩 드라이런**: `description`만으로 검색이 되는지(동의어 쿼리 3~5개) 점검한다. (JSON 파일 자체에 기록되지는 않으며, **PR/릴리스 전 수동·스크립트 검증**으로 수행.)
6. **UCM 시뮬레이션**: 통합 컬럼 후보 1개를 정해 `mapped_dp_ids`를 적어 본 뒤, 컬럼 설명 문장이 자연스러운지 검토한다. (시드 JSON과 동일하게 저장할 필요는 없으나, 설계 검토는 권장.)

---

## 7. 예시

### 예시 A — 요구사항 문단 → DP

**원문(발췌):**  
“조직은 전환 계획 실행으로 발생한 총 지출액을 금전적 가치와 보고 기간 중 발생한 총 지출액 대비 비율로 보고해야 한다.”

**추출 DP (요지):**

- `dp_id`: `GRI102-1-c` (공개 **102-1-c**에 대응; `GRI102-102-1-c` 형태는 사용하지 않음)
- `dp_code`: `GRI_102_DIS_1_C_EXPENDITURE` 등
- `name_ko`: “공개 102-1-c: 전환 계획 지출”
- `dp_type`: `quantitative`
- `unit`: `currency_krw` (또는 보고 통화에 맞는 단위); 원문이 금액·비율을 **별도 하위 항목**으로 두지 않았으면 한 DP에 규칙만 나열(§3.2.1·§3.3.2)
- `validation_rules` 예:  
  - “전환 계획 관련 지출 총액 보고”  
  - “당기 총 지출 대비 비율(%) 보고”  
  - “감사받은 연결 재무제표(또는 공개 재무정보)와 대조”

**포인트:** 검증 로직이 달라 보여도, **요구사항이 한 항목으로만 규정되고 로마숫자 등으로 쪼개져 있지 않으면** 한 `dp_id`에 두고 규칙·지침 rulebook으로 보완한다. **요구사항에 `i`·`ii`…가 열거되면** §3.2.1에 따라 각각 별도 `dp_id`(§3.3.2).

### 예시 B — 지침 블록 → Rulebook

**원문(발췌):**  
“전환 계획 지출 % = (전환 계획 지출 / 총 지출액) × 100 … CapEx와 OpEx로 구분하여 보고해야 한다.”

**추출 Rulebook (요지):**

- `rulebook_id`: `RULE_GRI102_1_C`
- `primary_dp_id`: `GRI102-1-c`
- `section_type`: `guidance` (`validation_rules.section_type`)
- `required_actions` 예:
  - `{ "action": "separate_capex_opex", "description": "CapEx와 OpEx로 구분 보고", "mandatory": true }`
  - `{ "action": "reconcile_with_audited_statements", "description": "감사 재무제표와 대조", "mandatory": true }`
- `verification_checks` 예:
  - `{ "check_id": "102_1_C_CAPEX_OPEX_SEPARATED", "description": "CapEx/OpEx 구분 여부", "expected": "capex_and_opex_separated" }`

### 예시 C — 조건부 공시

**원문:** “전환 계획이 없는 경우 그 이유와 조치·시간표를 기술하라.”

**DP:** `GRI102-1-j`  
**DP `validation_rules` 예:** “전환 계획이 없는 경우 사유·조치·예상 일정 명시” (조건을 DP에도 문장으로 남김)  
**Rulebook `required_actions` 예:**  
`{ "action": "explain_no_plan", "mandatory": true, "condition": "if_no_transition_plan" }`

---

## 8. 안티패턴 (피할 것)

- **원문 요구사항 목록에 없는 문자·번호로 `dp_id`를 새로 만들기** (예: 지침 블록만 있는데 `-l` 부여, 한 항목 문장을 원문에 없는 `-pct`/`-amount`로 분해) → §3.2.1 위반; rulebook·`validation_rules`로만 다룬다. (**반대로**, 요구사항에 `i`·`ii`가 있는데 한 DP에만 몰아넣는 것도 §3.2.1과 어긋난다.)
- **한 DP에 공개 3~5개 분량의 원문을 그대로 넣기** → 임베딩이 희석되고 매핑 정확도가 떨어진다.
- **`verification_checks`만 있고 DP에 검증 요지가 없음** → LLM이 DP 텍스트만 보고 판단할 때 실패한다.
- **`primary_dp_id`를 루트(`GRI102`)만 가리키기** → 검색 후보가 과도하게 넓어진다.
- **수치형인데 `unit` 누락** → UCM·Supervisor 검증 단계에서 거절 또는 오매핑.
- **동일 `check_id` 중복** → 자동 검증·로그 추적이 깨진다.

---

## 9. 검수 체크리스트 (요약)

**Data Point**

- [ ] 모든 `dp_id`가 **제공 원문의 공개·하위 항목**에 대응하는가 (임의 접미어·가상 항목 없음, §3.2.1)  
- [ ] 공시 경계가 명확하고, `dp_id`가 안정적인가  
- [ ] `description`이 검색·요약에 적합한가  
- [ ] `dp_type` / `unit` / `value_range`가 일치하는가  
- [ ] `parent_indicator` / `child_dps`가 순환·누락 없이 연결되는가  
- [ ] `validation_rules`가 서술·수치·조건부를 반영하는가 (조건부는 DP 문장 + rulebook `condition` 병행)  
- [ ] `equivalent_dps`가 실제 등록 DP 위주인가, 외부 라벨만 있는 항목은 추후 정리 계획이 있는가  

**Rulebook**

- [ ] `primary_dp_id`가 최적 수준(너무 상위 아님)인가  
- [ ] `section_content`에 계산식·예외·교차 참조가 빠짐없는가  
- [ ] `required_actions`와 `verification_checks`가 1:1 또는 N:1로 대응 가능한가 (지침도 가능하면 `verification_checks` ≥ 1)  
- [ ] `cross_references`가 `validation_rules` 내부에 있으며, “참조로 대체 가능”이 명시되어 있는가(해당 시)  

**UCM 연계**

- [ ] 동일 주제 통합 시 `mapped_dp_ids` 묶음이 자연스러운가  
- [ ] 통합 컬럼 설명(향후 `column_description`)을 한 문단으로 쓸 수 있는가  

---

## 10. 관련 문서

- [DATA_ONTOLOGY.md](./DATA_ONTOLOGY.md) — DP 스키마, `rulebooks`·`data_points` 테이블, 임베딩 필드 구성  
- [DATABASE_TABLES_STRUCTURE.md](./DATABASE_TABLES_STRUCTURE.md) — DB 반영 시 컬럼 확인  
- (서비스별) ESG 데이터 UCM 결정 정책 설계 — Accept/Review/Reject, 임베딩·룰·LLM 역할 분리

---

*문서 버전: 1.2 — §3.2.1 원천 일치 `dp_id` 원칙·§3.3.2·§4.2·§8·체크리스트 반영*
