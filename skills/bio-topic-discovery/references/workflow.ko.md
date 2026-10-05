# 실행과 프로파일

[English](workflow.md) | **한국어**

프로젝트 `README.ko.md`와 `profiles/deg.example.yaml`, `profiles/meta.example.yaml`에 지원 범위와 필드가 있습니다. 예제 데이터는 합성이므로 실제 연구에는 `synthetic_example: false`를 설정하세요.

```bash
python3 scripts/run.py plan --input /absolute/data.csv --profile /absolute/study.yaml --out /absolute/new-run
python3 scripts/run.py run --out /absolute/new-run
python3 scripts/run.py verify --out /absolute/new-run
python3 scripts/run.py status --out /absolute/new-run
```

프로파일은 `schema_version: 1`, `domain: deg|meta`, `question`, `columns`, `inspection`을 요구합니다. `columns`는 공통 필드 이름에서 원본 열 이름으로 대응합니다. DEG 필수 매핑은 entity_id, comparison이며 log2fc/FDR도 가능하면 매핑합니다. 메타분석 필수 매핑은 study_id, measure, value입니다. 원본에 없는 과학적 속성은 연구자가 확인한 `declarations`만 사용합니다.

`inspection.cell_fields`로 모든 행을 셀로 나눕니다. `pairs: all|within_groups|none`을 반드시 명시합니다. within_groups는 pair_group_by를 요구합니다. 같은 유전자·비교의 세포 간 쌍, 같은 결과 계열의 연구 간 쌍 등 연구 목적에 맞는 범위입니다. 필요하면 all을 사용하되 모든 n(n−1)/2개 쌍을 실제 검사합니다. 해당 범위와 비용을 계획 단계에서 알립니다.

기본 연산자는 integrity, heterogeneity, robustness, bias, gap, generalizability, contradiction, decision입니다. mechanism은 출처가 있는 knowledge_relations를 선언한 경우에만 사용합니다. relation의 source/target/type/source_reference를 구체적으로 제공하고 생물학적 사실과 가정을 구분하세요.

합성은 명시적으로 활성화한 meta만 지원합니다. CI 수준은 0.95처럼 0~1로 표현합니다. SE를 제공하면 비율 척도는 se_scale: log, 차이 척도는 identity를 선언합니다. CI 역산은 ci_method: wald, ci_distribution: normal을 확인한 경우만 합니다. source_blocked·hold_reason·synthesis_approved와 필수 메타데이터를 확인합니다. 같은 척도라도 추정 대상이나 보정 정의가 호환되지 않으면 셀을 나누거나 합성을 비활성화하세요.

새 실행 폴더에는 frozen input, profile.json, records.json, code snapshot, inspection.sqlite3가 있습니다. 실패한 계획의 .planning 폴더를 성공 실행으로 사용하지 않습니다. 코드가 바뀐 기존 실행은 원래 source 스냅샷으로 재개하거나 새 계획을 만듭니다. 재개 과정에서 입력 또는 프로파일을 고쳐 맞추지 않습니다.

`run --retry-failed`는 원인 해결 후만 사용합니다. 전수 실패는 verification.json과 개별 error로 확인합니다. 모델 가중치·서버·컨테이너를 임의로 변경하지 않습니다. 로컬 토크나이저 검증을 실행하려면 해당 컨테이너에 대한 읽기·실행 접근이 필요합니다.

기본 결과물: `candidates.csv`. 모든 후보와 원본 연결, 관측 근거, 한계, 반증·확인 사항, 검사·검증 상태를 담습니다. 최종 답변에 절대 경로 파일 링크를 제공합니다. 실행 응답의 `candidate_csv`에 경로가 있으며, `report --out PATH`는 검증 후 파일만 다시 내보냅니다. 복합 셀은 JSON이고 원본 ID는 세미콜론으로 구분하며 UTF-8 BOM을 사용합니다. 헤더만 있는 CSV는 선택된 후보가 없다는 뜻이며 `candidate-summary.json`과 검증 상태도 확인합니다.

보조 자료: `REPORT.ko.md`, `candidates.jsonl`, `decisions.jsonl`, `verification.json`, `SYSTEM2-REVIEW.ko.md`. 실제 응답이 모든 계획된 과제에 결합되었는지 verify가 검사합니다. 선택 확률은 과학적 진실 확률이 아닙니다.

메타분석의 기본 논문 수 가중치는 0.25입니다. 새 프로파일의 `ranking.paper_count_weight`(0~1)로 조정합니다. 수식·중복·상태 기준과 CSV 열은 `docs/candidate-csv.ko.md`를 참고하세요. 모델 검사 후 후보 순서에만 적용합니다.

## v0.3 임상 질문·분석 세트

메타분석은 `profiles/meta.clinical.example.yaml`과 엔진의 `docs/clinical-pipeline.ko.md`를 읽습니다. 상위 질문·층·민감도는 `clinical.partition`, 선택 규칙은 결과값을 사용하지 않는 `clinical.analysis_sets`, 생성 경위는 `clinical.question_registry`로 선언합니다. 원장은 범위를 지정한 `clinical.ledger_files`로 연결합니다. 분석 세트마다 선택 효과·중복 정책·독립성 수준·미결 관계를 확인하고, 후보–효과 연결표에서 모든 반대·무효 결과가 유지되는지 검증합니다. 단계별 원문·이중검토·결과별 RoB·승인은 전수 검사와 별도입니다. 논문 가점은 기본 0이며 중복 출판에 상한을 적용합니다. 위 구형 스키마·점수 설명은 `clinical.enabled: false` 재현용입니다. 새 임상 CSV의 목록 셀은 JSON입니다.

## v0.4

엔진의 `docs/long-evidence.ko.md`를 읽습니다. 새 프로파일에 `inspection.partition_long_evidence: true`를 지정하고 모든 조각과 원래 단위의 완료를 검증합니다. 조각별 검사와 전체 근거의 공동 판단을 구분합니다. `link-ledger`로 효과 ID를 정확히 연결하고 미연결·충돌·입력 밖 원장 행을 기록합니다. 없는 원장은 추정으로 복원하지 않습니다.
