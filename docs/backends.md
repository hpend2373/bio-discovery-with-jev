# Jev API / 로컬 Laya 연결

두 백엔드는 `{state, model, questions}` 요청에 대해 질문별 선택 결과와 확률 분포를 반환합니다. 이 구현은 선택형 판단을 사용하며, 자유문장 생성 모델처럼 구체적인 연구 질문을 작성하지 않습니다. 후보 구체화는 후속 단계로 필요합니다.

## Laya

```yaml
backend:
  kind: laya
  url: http://127.0.0.1:8000
  model: multilingual
  container: laya-local-laya-serve-1
  max_len: 4096
  head_max_len: 384
```

지원 설치는 reference Laya 서버의 `/health`에서 모델 리비전을 보고하고, 같은 리비전의 토크나이저에 Docker로 접근할 수 있어야 합니다. 컨테이너 이름은 사용자의 설치에 맞게 바꾸세요. 기본 토크나이저 경로는 컨테이너 내부 `/home/laya/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/<REVISION>/multilingual`입니다. 다른 위치는 `model_path`를 설정하되 리비전이 일치해야 합니다.

근거·질문·선택지가 모두 들어가는지 실제 토크나이저로 확인하고, 서버 보고 입력 토큰 수와 대조합니다. 잘린 근거는 성공으로 처리하지 않습니다. 일반적인 모든 Jev 호환 서버나 Docker 없는 설치를 지원한다고 보장하지 않습니다.

## Jev

```yaml
backend:
  kind: jev
  model: jev-1.13.0
  max_body_bytes: 262144
  timeout: 45
```

- API: `https://api.typesafe.ai/v1/systemone`.
- 인증: 환경변수 `TYPESAFE_API_KEY`의 Bearer 키.
- 실행: `run --allow-external`. 키나 플래그가 없으면 오류로 종료하며 Laya로 자동 전환하지 않습니다.
- `jev-latest`처럼 바뀔 수 있는 별칭 대신 고정된 `jev-x.y.z`를 사용합니다. 사용할 수 있는 버전은 자신의 계정과 공식 문서에서 확인하세요.
- 요청 크기 한도는 이 도구의 바이트 한도이며, 서비스의 실제 토큰 한도를 확인하는 보장은 아닙니다. 근거를 자동으로 잘라 보내지 않습니다.
- 전체 질문 목록, 모든 선택지의 확률, 선택 결과, 모델 버전, 요청 해시와 원본 근거 연결을 검사합니다.
- 일시적인 연결 오류·429·502·503·504에는 최대 3회 시도합니다. 인증 오류나 계속되는 실패는 미완료로 남습니다.

공식 계약: [API reference](https://docs.typesafe.ai/api), [Models](https://docs.typesafe.ai/models), 확인일 2026-10-01.

## 검증 수준

| 항목 | 상태 |
|---|---|
| 로컬 Laya 실제 데이터 전수 호출 | 56,040개 관점 판정 완료, 기록 검증 통과 |
| Laya 토큰·전체 근거 결합 | 실제 호출 + 합성 응답 단위 테스트 |
| Jev 요청·응답·키/외부 전송 제어·모델 버전·근거 결합 | 합성 응답 단위 테스트 통과 |
| Jev 실제 서비스 호출 | API 키가 없어 미실행 |
| 구체적 연구 질문·신규성 | 현재 구현 미달 / 신규성 검토 미완료 |
