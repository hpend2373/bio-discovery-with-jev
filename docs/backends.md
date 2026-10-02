# Jev API and local Laya

**English** | [한국어](backends.ko.md)

Both backends accept `{state, model, questions}` and return categorical choices and probability distributions. The current engine uses choice judgments; developing concrete research questions requires a subsequent step.

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

The supported reference installation must expose a model revision through `/health` and provide Docker access to the same revision's tokenizer. Adjust the container name for your installation. The default tokenizer path inside the container is `/home/laya/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/<REVISION>/multilingual`. A custom `model_path` must match that revision.

The tokenizer checks complete evidence, questions, and choices, then compares expected tokens with the server's reported input token count. Truncated inputs cannot count as successful inspections. Normal discovery commands reuse the existing server. Support for arbitrary compatible servers or Docker-free installations is not established.

## Jev

```yaml
backend:
  kind: jev
  model: jev-1.13.0
  max_body_bytes: 262144
  timeout: 45
```

- Endpoint: `https://api.typesafe.ai/v1/systemone`.
- Authentication: Bearer token from the `TYPESAFE_API_KEY` environment variable.
- Run with `--allow-external` to explicitly permit transmitting evidence. Missing keys or permission flags produce an error; there is no automatic fallback to Laya.
- Use a pinned `jev-x.y.z` version rather than a moving alias. Confirm available versions with your account and the official documentation.
- The byte limit belongs to this tool; it does not establish the service's actual token limit. Inputs are not silently shortened.
- Validation checks all question IDs, allowed choices, probability distributions, model versions, request hashes, and source evidence bindings.
- Temporary connection errors and HTTP 429/502/503/504 responses receive up to three attempts. Authentication errors and persistent failures remain incomplete.

Official contract: [API reference](https://docs.typesafe.ai/api) and [models](https://docs.typesafe.ai/models).

## Verification scope

Laya GPU use and complete-input response contracts were checked in the timing comparison. Jev request/response handling, external-transmission controls, and version bindings have synthetic contract tests. Live Jev service execution and computing time remain unverified. Response completeness does not establish the scientific validity of a research hypothesis. See [computing time and interpretation](evaluation/LATENCY.md).
