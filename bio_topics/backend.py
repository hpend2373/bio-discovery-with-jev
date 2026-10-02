import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .token_guard import TokenGuard
from .util import digest

DEFAULT_REVISION = "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"


def validate_response(payload, questions):
    if not isinstance(payload, dict) or not isinstance(payload.get("model"), str) or not payload["model"]:
        raise ValueError("실제 모델 ID가 없는 응답")
    answers = payload.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("모델 응답의 질문 목록 불일치")
    for name, q in questions.items():
        answer = answers[name]
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError("선택형 응답 형식 오류")
        probs = answer.get("probabilities")
        if not isinstance(probs, dict) or set(probs) != set(q["criteria"]):
            raise ValueError("모델 선택지 누락/추가")
        values = list(probs.values())
        if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in values):
            raise ValueError("유효하지 않은 모델 확률")
        if abs(sum(values) - 1) > 0.003:
            raise ValueError("모델 확률 합 오류")
        choice = answer.get("choice")
        if choice not in probs or probs[choice] < max(values) - 1e-5:
            raise ValueError("선택 결과와 확률 불일치")
    if payload.get("usage", {}).get("options"):
        raise ValueError("선택지 토큰 손실이 보고됨")
    return payload


def slice_receipt(receipt, operator, state, all_questions):
    """Retain the complete server response proving that every question was actually sent."""
    names = {name: operator + "__" + name for name in ("discovery", "focus")}
    payload = {**receipt["payload"], "answers": {name: receipt["payload"]["answers"][qid] for name, qid in names.items()}}
    return {"payload": payload, "context_receipt": receipt.get("context_receipt"),
            "provider_identity": receipt["provider_identity"], "question_bindings": names,
            "batch": {"state_hash": digest(state), "questions": all_questions,
                      "payload": receipt["payload"], "request_hash": receipt.get("request_hash")}}


def validate_receipt(receipt, state, questions, identity, all_questions, operator):
    validate_response(receipt["payload"], questions)
    if receipt["provider_identity"] != identity:
        raise ValueError("provider_binding")
    batch = receipt["batch"]
    if batch["state_hash"] != digest(state) or batch["questions"] != all_questions:
        raise ValueError("batch_evidence_binding")
    validate_response(batch["payload"], all_questions)
    for name in questions:
        qid = operator + "__" + name
        if receipt["question_bindings"].get(name) != qid or receipt["payload"]["answers"][name] != batch["payload"]["answers"][qid]:
            raise ValueError("question_binding")
    if identity["kind"] == "laya":
        guard = receipt.get("context_receipt") or {}
        if not guard.get("ok") or set(guard.get("question_lengths", {})) != set(all_questions):
            raise ValueError("full_context_questions")
        if guard["expected_input_tokens"] != sum(guard["question_lengths"].values()) or batch["payload"]["usage"]["input_tokens"] != guard["expected_input_tokens"]:
            raise ValueError("full_context_tokens")
    if identity["kind"] in ("laya", "jev"):
        body = {"state": state, "model": identity["model"], "questions": all_questions}
        if identity["kind"] == "laya":
            body.update(max_len=identity["max_len"], head_max_len=identity["head_max_len"])
        if batch["request_hash"] != digest(body):
            raise ValueError("full_request_binding")
    if identity["kind"] == "jev" and batch["payload"]["model"] != identity["model"]:
        raise ValueError("jev_model_version")


class HTTPBackend:
    def __init__(self, config, allow_external=False):
        self.config = config
        self.kind = config.get("kind", "laya")
        self.guard = None
        self.simulated = False
        if self.kind == "laya":
            base = config.get("url", "http://127.0.0.1:8000").rstrip("/")
            parts = urllib.parse.urlsplit(base)
            if parts.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("로컬 Laya 주소만 허용합니다. 외부 전송에는 Jev 모드를 명시하세요.")
            self.endpoint = base + "/v1/systemone"
            self.key = os.environ.get("LAYA_API_KEY")
            health = self._request(base + "/health")
            model = config.get("model", "multilingual")
            revision = health.get("revisions", {}).get(model)
            if health.get("status") != "ok" or not revision:
                raise RuntimeError("선택한 Laya 모델의 상태/리비전을 확인할 수 없습니다.")
            self.max_len = config.get("max_len", 4096)
            self.head_max_len = config.get("head_max_len", 384)
            if model != "multilingual" and self.max_len > 512:
                raise ValueError("v0.1의 긴 근거 검사는 multilingual 모델을 사용하세요.")
            checkpoint_suffix = "/multilingual" if model == "multilingual" else "/typed-decisions" if model == "typed-decisions" else ""
            model_path = config.get("model_path", "/home/laya/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/" + revision + checkpoint_suffix)
            if not model_path.rstrip("/").endswith("/" + revision + checkpoint_suffix):
                raise ValueError("서버 리비전과 토크나이저 경로가 일치하지 않습니다.")
            self.guard = TokenGuard(config.get("container", "laya-local-laya-serve-1"), model_path)
            self.identity = {"kind": "laya", "endpoint": self.endpoint, "model": model, "revision": revision,
                             "max_len": self.max_len, "head_max_len": self.head_max_len,
                             "token_guard": self.guard.identity}
        elif self.kind == "jev":
            if not allow_external:
                raise ValueError("Jev는 근거를 외부에 전송합니다. 명시적인 --allow-external이 필요합니다.")
            self.key = os.environ.get("TYPESAFE_API_KEY")
            if not self.key:
                raise ValueError("TYPESAFE_API_KEY가 없습니다. Laya로 자동 전환하지 않습니다.")
            self.endpoint = "https://api.typesafe.ai/v1/systemone"
            model = config.get("model", "")
            if not re.fullmatch(r"jev-\d+\.\d+\.\d+", model):
                raise ValueError("Jev 재개·캐시에는 고정 버전 ID(예: jev-1.13.0)를 선언하세요.")
            self.identity = {"kind": "jev", "endpoint": self.endpoint, "model": model,
                             "max_body_bytes": config.get("max_body_bytes", 262144)}
            limit = self.identity["max_body_bytes"]
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("max_body_bytes는 양의 정수여야 합니다.")
        else:
            raise ValueError("backend.kind는 laya 또는 jev여야 합니다.")

    def _request(self, url, body=None):
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        # Do not inherit an HTTP proxy for localhost or follow redirects with private evidence.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(url, data=body, headers=headers)
        with opener.open(request, timeout=self.config.get("timeout", 45)) as response:
            return json.load(response)

    def evaluate(self, state, questions):
        receipt = None
        body = {"state": state, "model": self.identity["model"], "questions": questions}
        if self.kind == "laya":
            receipt = self.guard.check(state, questions, self.max_len, self.head_max_len)
            body.update(max_len=self.max_len, head_max_len=self.head_max_len)
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        if self.kind == "jev" and len(encoded) > self.identity["max_body_bytes"]:
            raise ValueError("Jev 요청 크기 계약을 넘었습니다. 근거를 잘라 전송하지 않습니다.")
        for attempt in range(3):
            try:
                payload = self._request(self.endpoint, encoded)
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f"모델 HTTP 오류: {exc.code}") from None
                time.sleep(min(2 ** attempt, 4))
            except (TimeoutError, urllib.error.URLError):
                if attempt == 2:
                    raise RuntimeError("모델 연결/시간 초과 오류; 해당 검사는 미완료") from None
                time.sleep(min(2 ** attempt, 4))
        validate_response(payload, questions)
        if receipt is not None and payload.get("usage", {}).get("input_tokens") != receipt["expected_input_tokens"]:
            raise ValueError("서버가 읽은 토큰 수와 전체 근거 토큰 수가 불일치")
        if self.kind == "jev" and payload["model"] != self.identity["model"]:
            raise ValueError("응답 모델이 고정된 Jev 버전과 불일치")
        return {"payload": payload, "context_receipt": receipt, "provider_identity": self.identity,
                "request_hash": digest(body)}

    def close(self):
        if self.guard:
            self.guard.close()
