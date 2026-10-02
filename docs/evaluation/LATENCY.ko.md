# 컴퓨팅 시간과 결과 해석

[English](LATENCY.md) | **한국어**

![실측 요청 시간](latency-comparison.png)

**그림 캡션.** 동일한 근거 입력 30개를 모델별로 각각 2회 평가한 HTTP 요청 시간의 합입니다. 요청마다 16개 선택형 질문을 판단했습니다. 두 모델을 같은 NVIDIA GB10 GPU에 각각 단독 적재했습니다. 모델 로드·시작·워밍업 시간은 제외했으며 그림에는 실측값만 표시합니다.

## 실측 컴퓨팅 시간

| 모델 | 유효 요청 | 총 요청 시간 | 요청 시간 중앙값 |
|---|---:|---:|---:|
| Laya multilingual · GPU | 60/60 | 45.07초 | 0.78초 |
| Qwen3.6 35B · GPU | 60/60 | 251.84초 | 3.48초 |

이 표본에서 Qwen/Laya의 총 시간비는 **5.59배**, 차이는 **206.77초**였습니다.

| 회차 | Laya 요청 시간 | Qwen 요청 시간 | 모델별 요청 수 |
|---|---:|---:|---:|
| 첫 평가 | 22.46초 | 149.09초 | 30 |
| 같은 입력 반복 | 22.61초 | 102.75초 | 30 |

반복 평가에는 서버의 프롬프트·KV 캐시 효과가 포함될 수 있습니다. 새 근거를 사용한 독립 표본이 아닙니다. 전체 데이터셋의 처리 시간 추정치는 제시하지 않습니다.

## 결과가 보여주는 것

- **응답 완결성:** 모델별로 필수 선택 결과 960개를 모두 반환했고, 모든 선택이 해당 질문의 허용 항목에 속했습니다. 응답 계약을 통과했다는 의미이며 선택의 정답 여부를 검증한 것은 아닙니다.
- **판정 일치:** 960개 중 252개가 일치해 **26.25%**였습니다. 두 회차 모두 480개 중 126개가 일치했습니다. 같은 입력을 반복했으므로 960개의 독립 사례로 해석하지 않습니다. 기술적 일치율이며 우연 보정 일치도나 전문가 정답률은 계산하지 않았습니다.
- **컴퓨팅의 실용적 의미:** 이 선택형 검사 작업에서 Laya의 요청 시간이 더 짧았습니다. 빠른 처리는 선언된 모든 단위를 검사하는 비용을 줄이고 모델의 실제 판단을 추적 가능하게 기록하는 데 도움이 될 수 있습니다.
- **과학적 의미:** 낮은 일치율은 두 모델의 판단을 동일한 결과로 대체할 수 없음을 보여줍니다. 전문가 정답지, 가설 신규성 평가, 생물학적 검증, 통계적 유의성 검정은 수행하지 않았습니다. 유의미한 과학적 발견이나 동일한 발굴 품질이 입증된 것은 아닙니다. 후보 건수와 선택 확률은 검증된 연구 결과가 아닙니다.

현재 엔진은 선택형 판단과 템플릿 제목으로 후보를 표현합니다. 구체적이고 반증 가능한 연구 질문을 만들고 근거의 의미를 판단하려면 후속 검토가 필요합니다. Jev API의 실측 시간과 실제 출력 품질은 미측정입니다.

## 측정 방법

- 측정일: 2026-10-02. 장비: NVIDIA GB10, aarch64, NVIDIA 드라이버 580.159.03.
- Qwen: 로컬 Ollama `qwen3.6:35b`, Q4_K_M이며 모델 메타데이터는 36.0B입니다. **42/42 레이어 GPU 적재**와 실제 CUDA 연산 프로세스를 확인했습니다.
- Laya: multilingual 체크포인트의 CUDA 적재를 확인했습니다. 리비전은 [latency-results.json](latency-results.json)에 기록했고 CPU 폴백은 없었습니다.
- 동시 요청은 1개입니다. Qwen 측정 중에는 Laya를 중지했고, Laya 측정 전에는 Qwen을 언로드했습니다. 모델 순서는 고정했으며 각 회차의 요청 순서는 섞었습니다.
- 두 모델에 동일한 전체 근거·질문 정의·선택지를 제공했습니다. 근거를 자르거나 필수 질문을 줄인 응답은 인정하지 않습니다.
- 시간은 HTTP 요청 시작부터 응답 검증까지입니다. Laya의 토크나이저 검사도 포함합니다. Qwen은 선택 ID를 생성하고 Laya는 확률도 반환합니다. 자유문장 가설 작성과 Qwen의 확률 생성은 측정하지 않았습니다.
- Qwen 설정: `think=false`, temperature 0, seed `20261002`, context 32,768, 최대 출력 2,048토큰. 모든 질문 ID가 필수인 JSON 객체를 요청했습니다.
- 모델 시작·워밍업은 제외했습니다. 표본 중 한 입력을 워밍업에 사용했으므로 첫 평가도 완전한 캐시 미사용 조건은 아닙니다. 엔진의 답변 캐시는 사용하지 않았으며 서버의 네이티브 캐시는 허용했습니다.

## 기록과 재현

[latency-results.json](latency-results.json)에는 모델 정보, GPU 확인, 익명 표본 순번, 실측 시간과 집계 일치율이 있습니다. 원본 근거, 연구 식별자, 입력 해시, 데이터 규모와 원시 모델 답변은 제외했습니다. 집계에 사용한 근거 연결 기록은 비공개 로컬 실행에 보관합니다.

캡션 없는 영문 그래프 재현:

```bash
python -m pip install -e '.[plots]'
python scripts/plot_latency.py
```

한국어 축 레이블을 사용하려면:

```bash
python scripts/plot_latency.py --lang ko --font /path/to/Korean-font.otf --out /path/to/latency-ko.png
```

자신의 동결된 실행을 사용하는 새 시간 표본:

```bash
python scripts/benchmark_latency.py --run runs/YOUR_FROZEN_RUN \
  --out runs/YOUR_INITIAL_SAMPLE --model qwen3.6:35b --per-kind 10 --repeats 2
python scripts/benchmark_gpu.py --run runs/YOUR_FROZEN_RUN \
  --sample-run runs/YOUR_INITIAL_SAMPLE --out runs/YOUR_GPU_TIMING_RUN \
  --switch-containers
python scripts/export_latency.py --run runs/YOUR_GPU_TIMING_RUN \
  --out docs/evaluation/latency-results.json
python scripts/plot_latency.py
```

GPU 스크립트는 지정된 로컬 컨테이너를 중지·시작하고 GPU 사용을 확인합니다. 종료 시 Qwen을 언로드하고 Laya를 복구합니다. 컨테이너 이름은 설치 환경에 맞게 바꾸세요. 실행 폴더에는 원본 근거와 모델 응답이 저장되므로 비공개로 유지합니다. 공개 JSON은 집계만 남긴 자료이며 원시 실행 파일을 그대로 배포한 것이 아닙니다.
