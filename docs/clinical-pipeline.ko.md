# 임상 질문별 후보 탐색 (v0.2)

[English](clinical-pipeline.md) | **한국어**

새 메타분석 프로파일에는 임상 질문 방식이 기본 적용됩니다. 이전 실행은 저장된 소스로 재현하고, 새 버전에는 새 실행 폴더를 사용합니다. `clinical.enabled: false`는 기존 행·연산자 방식의 재현용입니다. DEG 동작은 유지됩니다.

처리 순서는 **원장 연결 → 확인된 표현 정규화 → 임상 질문별 분리 → 코호트 관계 반영 → Laya/Jev 전수 검사 → 후보 CSV**입니다. 미확인·배경·보류·차단 행도 모두 모델 검사에 포함됩니다.

## 사용

```bash
python -m bio_topics plan --input examples/meta-clinical.csv --profile profiles/meta.clinical.example.yaml --out runs/clinical-example
python -m bio_topics run --out runs/clinical-example
python -m bio_topics verify --out runs/clinical-example
```

Laya는 기존 로컬 서버를 사용합니다. Jev는 `profiles/meta.clinical.jev.example.yaml`과 명시적인 외부 전송 승인(`--allow-external`)을 사용합니다. 예제의 인구집단·약물·중복 관계는 모두 합성 데이터이므로 실제 프로젝트에 복사하지 마세요.

## 원장과 표현

`clinical.ledger`에는 논문(publications), 연구(studies), 참여자 집단(populations), 분석(analyses), 효과 행(effects)을 등록합니다. 각 항목은 `id`, `fields`, `confirmed`, `source_reference`를 갖습니다. 효과 행 ID부터 명시적으로 연결된 분석·참여자·연구·논문 ID를 따라갑니다. 제목 유사도로 자동 연결하지 않습니다.

`clinical.ledger_files`로 CSV/TSV/XLSX 원장을 매핑할 수 있습니다. 파일 경로는 프로파일 기준이며 `entity`, `path`, `id_column`, `columns`, `confirmed`, `source_reference`와 필요시 `sheet`를 선언합니다. 실행에는 원장 파일 복사본과 해시, 읽어들인 항목이 고정됩니다.

논문에서 상속할 수 있는 것은 서지 정보이며, 분석별 시점·약물·비교군을 논문 전체에 복사할 수 없습니다. 효과값·CI·승인·차단 상태도 이 메타데이터 원장에서 상속하지 않고 효과 표에서 직접 매핑합니다. 서로 다른 확인 값이 충돌하면 정규 필드는 미결로 두고 두 출처를 보존합니다. 미확인 연결은 제안으로만 남깁니다.

정규화 사전은 필드마다 `canonical`, `aliases`, `confirmed`, `source_reference`를 선언합니다. 확인된 동의어만 바뀌며 원래 값과 규칙을 보존합니다. 원본·연결·충돌·정규화 이력은 `records.json`과 `clinical-audit.json`에 기록됩니다. 척도 변환이나 누락 정보 추정은 하지 않습니다.

## 임상 질문과 검사 범위

필수 질문 축은 인구집단, 치료 단계, 약물군·약물 정의, 노출 시점, 비교군 유형·정의, 결과 정의·측정 시점입니다. 하위군·노출 시작·갱신 방식도 값이 있으면 질문을 구분합니다. `clinical.question_fields`로 필수 축을 추가할 수 있습니다. 필수 의미가 없거나 원장 충돌이 있으면 행별 미결 질문으로 남기며, 같은 unknown이라는 이유로 합치지 않습니다. 해당 없음은 연구자가 근거를 확인해 명시할 수 있습니다.

질문 안에서 추정 대상, 시간 원점, 설계, 척도·단위, 모형·보정, 용량·lag·기간을 분석 묶음으로 구분합니다. `clinical.analysis_fields`로 구분을 추가할 수 있습니다. `pairs: within_questions`는 같은 질문 안의 모든 행 쌍을 논문 경계를 넘어 검사합니다. 다른 범위가 필요하면 `all`, `within_groups`와 `pair_group_by`, `none`을 명시합니다. 임상 방식의 셀은 질문 ID로 구성되며 공통 프로파일의 `cell_fields`가 이 경계를 바꾸지는 않습니다.

기술 통계는 `analysis_role: context`로 선언하면 검사와 질문 연결을 유지하면서 효과 근거 가점에서 제외됩니다. 지원되는 비교 척도는 기본 effect, 다른 미지정 척도는 unresolved로 남깁니다.

## 코호트와 집계

실제 참여자 표본을 가리키는 `population_id`를 우선 사용합니다. 없으면 하나의 명시적 코호트 ID를 쓰며, 한 효과에 여러 코호트가 합쳐졌으면 미결 결합 단위로 남깁니다. 연구 ID만으로 독립성을 인정하지 않습니다.

`clinical.cohort_relations`는 `population:ID` 또는 `cohort:ID` 사이의 동일(same), 부분 중복(partial_overlap), 포함(contains: 왼쪽이 오른쪽을 포함), 비중복(disjoint), 미상(unknown)을 기록합니다. `confirmed`, `source_reference`가 필요하며 `question_scope`로 적용 질문 속성을 제한할 수 있습니다. population_id가 있는 행의 관계는 population ID로 선언하세요. 같은 넓은 코호트 안의 기간·하위 표본은 별도 population ID로 구분합니다.

확인된 동일 집단은 묶고, 부분 중복·포함 관계는 원래 관계를 보존합니다. 서로 다른 집단 ID라는 이유만으로 독립성을 인정하지 않습니다. 모든 효과 근거 집단의 신원이 있고 서로 비중복임이 확인될 때만 독립 근거 수를 출력합니다. 부족하면 CSV는 빈 값, JSON은 null, 상태는 unresolved입니다. 부분 중복의 유효 표본 수나 공분산을 추정하지 않습니다.

| 항목 | 의미 |
| --- | --- |
| paper_count | 서로 다른 논문 ID 수. 연구 ID로 대체하지 않음 |
| unique_study_count | 서로 다른 연구 ID 수 |
| missing_paper_identity_rows | 논문 연결이 미완료인 행 수 |
| cohort_count / population_count | 코호트 ID / 참여자 집단 식별자 수 |
| known_dependency_group_count | 알려진 중복 연결 묶음 수. 독립 근거 수와 다름 |
| independent_evidence_count | 인용한 효과 근거의 확인된 독립 단위 수. 미확정이면 빈 값 |
| unresolved_independence_count | 독립성 확인이 남은 집단 묶음 수 |
| eligible_evidence_count | 질문 정보·효과값이 유효하고 연결 충돌·보류·차단이 없는 탐색 근거 단위 수 |
| eligible_independent_evidence_count | 적격 근거만 대상으로 확인한 독립 단위 수 |
| eligible_paper_count | 적격 효과 근거를 제공하는 논문 수 |

여기서 적격은 후보 탐색 가점의 조건이며 합성 승인이 아닙니다. 합성에는 승인, 유효한 불확실성, 분석 호환성과 확인된 독립성도 필요합니다. 동일 참여자는 한 추정치씩 선택하고, 미해결 중복은 합성을 막으며 계획 단계에 사유를 남깁니다.

## 순위와 결과

같은 경로·연산자 안에서 질문 완결성, 검토에 필요한 정보, 적격 근거 유무를 먼저 봅니다. 이후 다음 가점을 적용합니다.

```text
점수 = 0.25 × log2(1 + 적격 논문 수)
     + 0.50 × log2(1 + 적격 근거의 확인된 독립 단위 수)
```

`ranking.paper_count_weight`, `ranking.independent_evidence_weight`로 각각 0~1을 설정합니다. 독립성이 미확정이면 독립 가점은 0입니다. 같은 참여자의 추가 논문은 논문 항에만 기여할 수 있습니다. 모든 세부 검사를 합친 고유 근거 행에서 수를 다시 계산하므로 검사 반복이 근거 수를 늘리지 않습니다. 점수는 우선순위 규칙이며 통계적 유의성이나 과학적 참일 확률이 아닙니다.

- `candidates.csv`: 임상 질문 집합·연산자·검사 초점·실행 경로별 후보 묶음. 분석 묶음, 모든 검사 ID, 원본 행 ID를 보존합니다.
- `inspection_results.csv`: 배경 판정·실패·미검사를 포함한 전체 계획 검사와 후보 연결입니다.
- `clinical-audit.json`: 원장 연결·정규화와 코호트 관계 기록입니다.

목록을 포함한 구조화 CSV 셀은 JSON이며 UTF-8 BOM을 사용합니다. 독립 근거 수의 빈 값은 0이 아닙니다. 두 CSV 모두 검사·검증 상태를 표시합니다.

현재 모델은 범주를 판정하고 질문 문구는 템플릿으로 구성합니다. 후보 묶음을 서로 다른 신규 과학 가설의 확정 목록으로 해석하지 마세요. 변형별 판단은 세부 검사에 남으며 문헌·반증 조건·반대 근거·사람의 채택은 후속 검토입니다. 입력 길이를 넘는 근거는 자르지 않고 실패로 표시하며 자동 긴 카드 분할은 아직 지원하지 않습니다.
