# 후보 CSV

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
| `status` | 후보의 후속 검토 상태. |
| `inspection_status`, `verification_status`, `inspection_coverage` | 검사 완료 상태, 기록 검증 상태와 0~1 검사율. 미완료 결과는 임시 결과입니다. |

UTF-8 BOM, 표준 CSV 인용 규칙과 영문 열 이름을 사용합니다. 현재 자동 생성 질문은 한국어입니다. 복합 근거는 JSON으로 보존하므로 짧은 요약문으로 줄이면서 정보가 누락되지 않습니다. JSONL과 Markdown 보고서는 보조 파일입니다.

후보가 없으면 헤더만 있는 CSV를 생성합니다. `candidate-summary.json`과 검증 상태를 함께 확인해 유효한 빈 결과와 미완료 검사를 구분하세요. 원본 근거가 포함된 파일은 명시적인 공개 허락이 없으면 비공개로 유지합니다.
