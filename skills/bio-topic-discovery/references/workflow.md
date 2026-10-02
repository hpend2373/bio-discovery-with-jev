# 실행과 프로파일

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

최종 파일: REPORT.ko.md, candidates.csv, candidates.jsonl, decisions.jsonl, verification.json, SYSTEM2-REVIEW.ko.md. 실제 응답이 모든 계획된 과제에 결합되었는지 verify가 검사합니다. 후보 선택 확률은 해당 가설의 참일 확률이 아닙니다.
