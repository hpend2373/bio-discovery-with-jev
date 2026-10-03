# 후보 CSV


> v0.3 메타분석 기본 CSV는 [임상 질문 방식](clinical-pipeline.ko.md)을 사용합니다. 아래 행·연산자별 스키마와 점수식은 DEG 및 `clinical.enabled: false`의 기존 방식에 해당합니다.
[English](candidate-csv.md) | **한국어**

`candidates.csv`가 기본 전달 결과물입니다. `run`에서 자동 생성하고 `candidate_csv`에 절대 경로를 반환합니다. 검증된 `report --out PATH`는 모델 호출 없이 파일을 다시 내보냅니다. 추가 확인 항목을 포함해 모든 후보를 유지합니다.

| 열 | 의미 |
|---|---|
| `rank`, `id` | 다양성을 반영한 순서와 후보 ID. 순위는 과학적 가치 점수가 아닙니다. |
| `route`, `operator`, `focus`, `question` | 연구 가설/추가 확인 경로, 검사 관점, 초점과 후보 질문. |
| `scope_text`, `scope` | 읽기 쉬운 범위 설명과 JSON 형태의 범위. |
| `record_ids`, `unit_id`, `job_id` | 원본 행·근거 단위·모델 검사에 연결되는 ID. 원본 ID는 세미콜론으로 구분합니다. |
| `observations`, `limits`, `required_checks` | 관측 사실, 근거 한계와 미결 원본 확인 사항을 담은 JSON 셀. 확인 목록이 비어 있어도 과학적 검토 완료를 뜻하지 않습니다. |
| `falsification` | 반증·검토 메모. 현재 엔진은 구체적인 반증 설계를 미결로 남기며 지어내지 않습니다. |
| `model`, `model_choice`, `model_selection_probability` | 모델과 실제 선택형 판단. 선택 확률은 가설의 진실·신규성 확률이 아닙니다. |
| `paper_count`, `unique_study_count`, `paper_count_basis`, `missing_paper_identity_rows` | 후보가 인용한 논문·연구 수, 연구 ID의 논문 수 대체 여부와 식별 불가 행 수. 식별 불가 행은 가점에서 제외합니다. |
| `incentive_evidence_count`, `paper_count_bonus`, `ranking_score`, `ranking_paper_count_weight` | 중복·상태를 반영한 가점 근거 수, 논문 수 가점, 합산 선정 점수와 가중치. 점수는 확률이 아닙니다. |
| `status` | 후보의 후속 검토 상태. |
| `inspection_status`, `verification_status`, `inspection_coverage` | 검사 완료 상태, 기록 검증 상태와 0~1 검사율. 미완료 결과는 임시 결과입니다. |

UTF-8 BOM, 표준 CSV 인용 규칙과 영문 열 이름을 사용합니다. 현재 자동 생성 질문은 한국어입니다. 복합 근거는 JSON으로 보존하므로 짧은 요약문으로 줄이면서 정보가 누락되지 않습니다. JSONL과 Markdown 보고서는 보조 파일입니다.

후보가 없으면 헤더만 있는 CSV를 생성합니다. `candidate-summary.json`과 검증 상태를 함께 확인해 유효한 빈 결과와 미완료 검사를 구분하세요. 원본 근거가 포함된 파일은 명시적인 공개 허락이 없으면 비공개로 유지합니다.

## 메타분석 논문 수 가점

같은 경로·연산자 안에서 기본 선정 점수는 다음과 같습니다.

`ranking_score = model_selection_probability + 0.25 × log₂(1 + incentive_evidence_count)`

후보에 연결된 사용 가능한 논문이 많을수록 가점이 커지며, 증가 폭은 점차 작아집니다. 가점 근거 수가 1·2·4·8이면 가점은 약 0.250·0.396·0.580·0.792입니다. 점수는 1을 넘을 수 있으며 통계적 유의성·확실성·신규성이나 합성 허용을 뜻하지 않습니다. 경로·연산자별 다양성 순서를 유지하므로 전체 순위는 단일 점수 내림차순 목록이 아닙니다.

프로젝트 전체 논문 수가 아니라 후보가 실제 인용한 행만 셉니다. 가능하면 `publication_id`에 DOI·PMID 같은 일관된 논문 ID를 매핑하세요. 없으면 `study_id`를 논문 수 대체값으로 사용하고 CSV에 표시합니다. 같은 논문의 여러 행, 같은 연구의 여러 논문, 선언된 중복 코호트는 연결된 한 묶음으로 처리합니다. 각 묶음은 식별 가능하고 보류·차단되지 않은 행이 있을 때만 가점 근거 1개를 제공합니다. 보류·차단 행도 전수 검사하고 결과에 유지합니다. 코호트 연결 정보가 없다고 독립성이 입증되지는 않으며, 논문 수는 원문·편향 위험 검토를 대체하지 않습니다.

새 프로젝트 프로파일에서 가중치를 바꿀 수 있습니다(0~1, 0이면 가점 해제).

```yaml
ranking:
  paper_count_weight: 0.25
```

가점은 메타분석의 전체 모델 검사 후에만 적용합니다. 논문이 적은 후보도 삭제하지 않고 검사 범위도 줄이지 않습니다. DEG에는 이 가점을 적용하지 않습니다. 기존 실행의 고정 코드·프로파일은 보존하며, 수정된 코드로 재실행하려면 새 검사 계획을 만드세요.
