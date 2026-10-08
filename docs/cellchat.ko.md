# CellChat 결과 검사

[English](cellchat.md) | **한국어**

`bio-topics cellchat` 명령으로 CellChat 결과를 검사합니다. DEG 표에서 CellChat을 새로 계산하거나 통신 점수를 DEG 효과값으로 합치는 기능은 아닙니다.

## 공식 문서에서 확인한 의미

2026-10-08에 [공식 저장소](https://github.com/jinworks/CellChat), [결과 추출 소스](https://github.com/jinworks/CellChat/blob/main/R/analysis.R), [추론 소스](https://github.com/jinworks/CellChat/blob/main/R/modeling.R)를 확인했습니다.

- `net$prob`, `net$pval`은 송신 세포 × 수신 세포 × 상호작용 배열입니다. 점수는 추론된 통신 강도이며 p값은 순열검정 결과입니다. DEG FDR·조건 간 차이 검정·실제 통신 확률과 다릅니다.
- `subsetCommunication()`은 단일 객체에서 표, 병합 객체에서 데이터셋별 목록을 반환합니다. 기본 추출에는 유의성 필터와 0값 제거가 적용됩니다. 임계값을 높여도 0값은 복원되지 않습니다.
- `netP$prob`은 상위 단계에서 선택된 근거의 경로 합계입니다. 리간드–수용체 행이나 그 p값과 섞지 않습니다.
- 복합체·보조인자와 CellChatDB v2의 비단백질 신호를 보존합니다. 이름의 밑줄로 복합체를 임의 분해하지 않습니다.
- 공식 문서의 Spatial CellChat v3는 별도 저장소입니다. 이번 지원 범위는 v1/v2의 세포군 수준 내보내기입니다.

## 입력과 실행

기존 CSV의 필수 열은 `source`, `target`, `interaction_name`, `prob`입니다. 나머지 원본 열도 보존합니다. 경로 표는 프로파일에 `level: pathway`를 선언하고 `interaction_name` 대신 `pathway_name`을 사용합니다. 기존 CSV는 **제공된 행만 전수 검사**하며, 빠진 연결을 0으로 채우지 않습니다.

전체 저장 배열은 R에서 내보냅니다. RDS를 Python에서 직접 읽지는 않습니다.

```r
source("scripts/export_cellchat.R")
export_cellchat(list(before = cellchat_before, after = cellchat_after),
                out = "cellchat-export", database_version = "사용한 DB 버전")
```

이 함수는 CellChat·jsonlite가 필요합니다. 저장 배열의 0·비유의값, 축, 행 수, 모형 설정, 복합체·보조인자를 보존합니다. 이미 상위 분석에서 제거된 근거까지 복구하지는 못합니다. 원래 저장 배열 전체를 검사한 것과 모든 생물학적 관계를 검사한 것은 구분합니다.

선택 인자 `contexts`는 데이터셋당 한 행의 표입니다. `dataset_id`, `condition`, `patient_id`, `species`, `analysis_group`, `cellchat_version`, `database_version`을 설정할 수 있습니다. 단일 객체 ID는 목록 이름, 병합 객체 ID는 `객체이름/멤버이름`입니다. 미확인은 unknown으로 두고, 환자 혼합 객체에 가상의 환자 ID를 붙이지 않습니다.

`analysis_group`을 같은 값으로 선언하면 조건 간 기술적 비교 질문을 추가합니다. 전처리·DB·세포 정의·population.size·공간 설정 등 비교 가능성을 먼저 확인하세요. 환자 단위 차이 검정이나 독립 반복 수를 자동 생성하지 않습니다.

```bash
bio-topics cellchat plan --input cellchat-export/manifest.json \
  --profile profiles/cellchat.example.yaml --out runs/cellchat-study
bio-topics cellchat run --out runs/cellchat-study
bio-topics cellchat verify --out runs/cellchat-study
```

기존 CSV는 `--input 결과.csv`로 넣습니다. 예제 프로파일의 연구 질문과 맥락을 실제 연구에 맞게 수정하세요. 기본 백엔드는 로컬 Laya입니다. Jev는 고정 모델 버전과 `TYPESAFE_API_KEY`를 설정하고 `run --allow-external`로 외부 근거 전송을 명시해야 합니다. 실제 Jev API 실행은 이번 검증에 포함되지 않았습니다.

## 효율과 검증 경계

같은 방향의 연결 근거를 카드로 공유하며 카드당 해당 질문만 검사합니다. 조건 비교는 비교 가능성이 선언된 경우에 추가합니다. 반대 방향·다른 종·DB/소프트웨어 버전·경로 수준을 구분하고, 미확정·0·약한 결과도 유지합니다. 중복 행의 원본 ID는 남기되 독립 근거로 세지 않습니다.

추론 전에 모든 카드의 전체 길이를 검사합니다. 너무 긴 카드는 자르지 않고 재설계가 필요하다고 중단합니다. 이 모드의 자동 분할·전체 통합은 미지원이며, 여러 카드를 하나의 GPU 요청에 묶지는 않습니다. 같은 카드의 질문은 한 요청에서 공유합니다. 근거·질문·코드·모델이 완전히 같은 검사는 재사용하고, 연속 실패 3회면 원인을 해결한 뒤 재시도합니다. 업그레이드 후 기존 실행 재개에는 실행 폴더의 `source/`를 사용합니다.

기본 산출물은 `candidates.csv`입니다. `candidate_evidence.csv`에 원본 행 순번·해시가 연결되고, `inspection_results.csv`에는 배경을 포함한 모든 판단이 남습니다. `row-card-links.csv`, 입력·프로파일·코드·원시 응답·검증 기록도 저장합니다. 부분 결과는 `incomplete_or_invalid`로 표시합니다.

별도 DEG 파일과의 자동 연결, 환자 단위 차이 검정, CellChat 상위 분석 자체의 재검증은 이번 범위에 없습니다. Python 합성 테스트와 GPU Laya의 작은 합성 CSV로 입력–검사–출력 경로를 검증합니다. R이 없는 환경이므로 R 내보내기 도우미의 실제 객체 실행은 아직 검증하지 못했습니다. 실제 객체의 내보내기 manifest를 먼저 검증해야 합니다.
