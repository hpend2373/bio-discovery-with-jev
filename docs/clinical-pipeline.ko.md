# 임상 질문·분석 세트별 후보 탐색 (v0.3)

[English](clinical-pipeline.md) | **한국어**

원장 연결 → 확인된 정규화 → 질문 계층 → 분석 세트 구성 → Laya/Jev 전수 검사 → 후보·효과 연결표 순서로 실행합니다. **검사 완료, 원문 확인, 독립 이중검토, 결과별 RoB 평가, 합성 승인은 별도 상태입니다.**

## 실행과 이전 버전

```bash
python -m bio_topics plan --input examples/meta-clinical.csv --profile profiles/meta.clinical.example.yaml --out runs/clinical-example
python -m bio_topics run --out runs/clinical-example
python -m bio_topics verify --out runs/clinical-example
```

기존 로컬 Laya 서버를 사용합니다. Jev는 `profiles/meta.clinical.jev.example.yaml`과 명시적 외부 전송 승인(`--allow-external`)을 사용합니다. 예제의 과학적 정의는 합성 데이터용입니다. 새 코드·규칙에는 새 실행 폴더를 사용하고, 기존 실행은 저장된 소스로 재현합니다. DEG 동작은 유지됩니다.

v0.2의 `question_fields`·`analysis_fields`는 `clinical.partition`으로 교체합니다. `independent_evidence_weight`는 제거하세요. 독립 근거는 가산점 대신 우선순위 단계로 다룹니다. 이전 필드는 자동으로 의미를 바꾸지 않고 이전 안내 오류를 반환합니다.

## 원장과 정규화

논문·연구·참여자 집단·분석·효과 행을 `clinical.ledger`에 명시적 ID로 연결합니다. 항목에는 `id`, `fields`, `confirmed`, `source_reference`가 필요합니다. CSV/TSV/XLSX 원장은 `clinical.ledger_files`에서 파일·ID열·필드 매핑을 지정합니다. 상대 경로는 프로파일 기준이며 원장 복사본·해시·읽은 항목을 실행에 고정합니다.

논문 전체에서 특정 분석의 시점·비교군을 상속하지 않습니다. 효과값·CI·검토 상태·승인은 효과 행에서 직접 매핑합니다. 확인된 동의어 사전만 정규화에 사용하며, 원본·제안·충돌·연결·정규화 이력을 보존합니다. 미확인 값이나 독립성을 모델 추정으로 채우지 않습니다.

## 질문은 세 계층으로 구성합니다

기본 상위 질문은 **약물군 + 노출 시점 + 결과 정의**입니다. 모집 집단·치료 단계는 비교 층, 비교군·모형·lag·추적기간 등은 대안 분석으로 둡니다. 모형이나 추적기간이 다르다는 이유만으로 상위 질문 ID가 달라지지 않습니다.

```yaml
clinical:
  partition:
    question: [exposure_class, exposure_timing, outcome_definition]
    stratum: [population, treatment_stage]
    sensitivity: [exposure_definition, comparator_type, comparator_definition,
                  outcome_time, model, lag, dose, exposure_duration]
```

각 항목을 어느 계층에 둘지 프로파일에서 선언합니다. 필수 상위 의미가 없는 경우만 미결 질문으로 분리합니다. 모집 집단 같은 아래 계층의 누락은 상위 질문을 나누지 않으며 해당 층의 분석 선택을 보류합니다. 척도·추정 대상·시간 원점·노출·비교군·결과 정의·인구집단 등 기본 합성 호환성은 계층 설정에서 빠져도 분석 묶음에 보존합니다.

`pairs: within_questions`는 같은 상위 질문의 모든 쌍을 비교합니다. 서로 다른 층 사이의 비교도 검사할 수 있지만 합성을 승인하는 것은 아닙니다. 결과에 따라 검사 쌍을 제외하거나 상위 일부만 선택하지 않습니다.

## 독립 근거 수는 분석 세트의 속성입니다

`analysis_sets.csv`에 선택한 원본 행 ID·효과 행 ID, 적용 규칙, 중복 처리 방식, 독립성 근거, 미해결 관계, 선택 단위 수, 사용 가능한 독립 단위 수를 기록합니다. 미확정 독립 단위 수는 빈 값(JSON null)이며 0과 다릅니다. 선택된 효과가 없는 세트는 0과 제외 사유를 함께 기록합니다.

실제 표본의 `population_id`를 우선 사용하고, 없으면 명시된 단일 코호트 ID를 사용합니다. 논문·연구 ID가 다르다고 독립적이라고 판단하지 않습니다. 코호트 관계는 동일·부분 중복·포함·비중복·미상이며 출처, 확인 상태, `evidence_level`, `rationale`를 기록합니다.

| 근거 수준 | 의미 |
| --- | --- |
| participant_linkage | 참여자 직접 연결·대조를 문서로 확인 |
| documented_sampling | 기관·기간·모집 기준 등 문서화된 표본 설계로 관계 판단 |
| author_confirmation | 출처가 있는 저자 확인 |
| inferred_design | 설계상 추정으로 독립성 확정에는 사용하지 않음 |
| unspecified | 충분한 근거 수준이 없어 미결로 유지 |

기본적으로 앞의 세 수준을 인정하며 `independence_policy.accepted_levels`로 더 제한할 수 있습니다. 참여자 ID 직접 대조만 요구하지 않습니다. 다만 확인 플래그 하나만으로는 독립성을 인정하지 않으며 모델이 근거의 진위를 자동 인증하지도 않습니다.

중복 처리에서는 **함께 선택할 때 알려진 중복이 없는 모든 최대 분석 세트**를 만듭니다. A–B, B–C가 겹쳐도 A–C가 비중복이면 A+C 세트와 B 단독 세트를 각각 유지합니다. 미상 관계도 남기며 독립성이 미결인 세트는 합성하지 않습니다. 부분 중복의 공분산을 추정하는 모형은 아직 지원하지 않습니다.

## 유리한 추정치를 대표로 고르지 않습니다

모든 탐색적 대안은 유지합니다. 별도 `analysis_sets` 규칙으로 주 분석 후보·대안 모형·민감도 역할을 선언할 수 있습니다.

```yaml
clinical:
  analysis_sets:
    - id: protocol_adjusted
      role: primary_candidate
      where: {model: adjusted}
      selection_timing: before_data_review
      source_reference: protocol_section_4
      reason: 사전에 정한 보정 정의
```

효과값·p값·CI·방향·유의성·SE를 선택 기준으로 쓰는 설정은 거부합니다. 주 분석 후보는 최종 채택이 아니며, 다른 대안을 지우지 않습니다. 같은 질문의 반대·무효·유리한 결과와 모델이 배경으로 판정한 행도 동일하게 후보–효과 연결표에 남깁니다.

## 질문의 생성 경위

등록되지 않은 발견 질문은 기본 `posthoc_exploratory`입니다. `question_registry`로 기존 프로토콜(`protocol`), 데이터 검토 후 추가(`posthoc_exploratory`), 후속 검증용(`validation_hypothesis`)을 구분합니다. 정확한 상위 질문 scope, ID, 출처, 생성일, 데이터 검토 전 여부를 선언해야 합니다. 프로토콜 질문은 검토 전에 등록했다는 선언이 필요하며, 사용자 선언이라는 상태를 명시합니다.

기존 프로토콜 질문을 탐색하다 새로 만든 가설도 `generated_hypothesis_origin: posthoc_exploratory`로 기록합니다. 프로토콜 질문이라는 이유로 새 가설까지 사전 지정으로 표시하지 않습니다.

## 검토 우선순위

같은 경로·연산자 안에서 독립 근거 우선순위는 질문 전체에 적용하고, 정밀도 수치는 같은 분석 축에서만 비교합니다. 순서는 다음과 같습니다.

1. 질문의 완결성·사용 가능한 분석 세트
2. 분석 세트별 독립 근거와 비교 가능한 정밀도
3. 결과별 RoB
4. 자료 완전성
5. 선택적으로 켠 출판 가점

전체 비어 있지 않은 분석 세트의 보수적 범위를 사용합니다. 최소 확인 독립 단위 수, 최소 비교 가능 정밀도, 가장 불리한 RoB, 최소 완전성을 보며 유리한 대표 추정치를 선택하지 않습니다. 정밀도는 독립성·SE가 유효하고 척도·단위·추정 대상·시간 원점·결과·층이 같은 경우에만 계산·비교합니다. 서로 비교할 수 없는 정밀도는 빈 값으로 남깁니다.

논문 수는 계속 별도 표시합니다. 논문 가점 기본값은 **0**이며, `paper_count_weight`를 켜도 확인된 선택 참여자 집단당 최대 1회만 인정합니다. 독립성이 미결이면 출판 가점도 주지 않습니다. 한 코호트의 반복 논문 다섯 편이 다섯 가점을 얻지 못합니다. 이 가점은 마지막 동점 구분용이며 `ranking_score`가 전체 순위식을 뜻하지 않습니다. **검토 우선순위는 통계적 합성 가중치나 근거 확실성 점수가 아닙니다.**

## 검토 상태와 합성 조건

효과 행에서 다음 정보가 명시되어야 합니다.

| 상태 | 필요한 입력 |
| --- | --- |
| 원문 확인 | source_verification_status=full_text_verified 및 source_verification_reference |
| 독립 이중검토 기록 | dual_review_status=agreed, dual_review_independent=true, 서로 다른 reviewer_ids 2개 이상, dual_review_reference |
| 결과별 RoB | rob_status=assessed, rob_judgment=low/some_concerns/high, 도구·출처, 해당 결과와 일치하는 rob_outcome_definition |
| 합성 승인 | synthesis_approved=true |

이 정보와 추정치·불확실성·호환성·선택 세트의 독립성이 모두 충족되어야 `synthesis_ready`가 됩니다. 실제 합성에는 별도의 `synthesis.enabled`도 필요합니다. ready는 합성을 이미 수행했다는 뜻이 아닙니다. 원문 조회, 실제 독립 이중검토, RoB 판정은 모델 전수 검사로 대체하지 않습니다.

## 결과 파일

| 파일 | 내용 |
| --- | --- |
| candidates.csv | 상위 질문별 후보 묶음, 생성 경위, 층·분석 세트 연결, 논문 수, 검토 우선순위 |
| inspection_results.csv | 배경·실패·미검사를 포함한 모든 계획 검사 |
| analysis_sets.csv / jsonl | 선택 효과, 중복 처리, 세트별 독립성·정밀도·검토 상태·보류 사유 |
| candidate_effects.csv | 후보–효과–세트 연결 및 주 분석 후보 / 대안 모형 / 민감도 / 배경 / 보류 역할 |
| clinical-audit.json / records.json | 원본·원장 연결·정규화·충돌·질문 계층 |

구조화 CSV 셀은 JSON이며 UTF-8 BOM을 사용합니다. 후보 문구는 여전히 범주 판정에 기반한 템플릿입니다. 독립적인 새 가설의 확정 목록이 아니며 문헌 신규성·구체적 반증 계획·사람의 채택은 후속 검토가 필요합니다. 입력이 길면 자르지 않고 실패로 표시합니다. 기존 시간 비교 그래프는 확장된 v0.3 전체 파이프라인의 속도 측정값이 아닙니다.
