# Computing time and result interpretation

**English** | [한국어](LATENCY.ko.md)

![Measured request time](latency-comparison.png)

**Figure caption.** Sum of measured HTTP request times for the same 30 evidence payloads, evaluated twice by each model, with 16 categorical questions per request. Both models used the same NVIDIA GB10 GPU in separate phases. Model loading, startup, and warmup are excluded. The figure contains measured values only.

## Measured computing time

| Model | Valid requests | Total request time | Median request time |
|---|---:|---:|---:|
| Laya multilingual · GPU | 60/60 | 45.07 s | 0.78 s |
| Qwen3.6 35B · GPU | 60/60 | 251.84 s | 3.48 s |

The Qwen/Laya total time ratio was **5.59×**, with a difference of **206.77 seconds** in this sample.

| Pass | Laya request time | Qwen request time | Requests per model |
|---|---:|---:|---:|
| First evaluation | 22.46 s | 149.09 s | 30 |
| Repeat of the same payloads | 22.61 s | 102.75 s | 30 |

The repeated pass may benefit from native prompt/KV caches. It is not an independent sample of new evidence. No full-dataset runtime projection is reported.

## What the results establish

- **Response completeness:** each model returned all 960 required choices. Every choice belonged to its question's allowed options. This validates the output contract, not the correctness of the selected option.
- **Paired choice agreement:** 252 of 960 choices agreed (**26.25%**), including 126/480 in each pass. Repeated judgments use the same inputs and must not be treated as 960 independent cases. Agreement is descriptive; no chance-adjusted agreement or expert accuracy score was computed.
- **Practical computing value:** Laya completed this categorical inspection workload with less measured request time. Faster processing can reduce the cost of inspecting all declared units, while preserving an auditable record of what each model actually judged.
- **Scientific meaning:** the low agreement shows that the two models' judgments are not interchangeable on this task. No expert ground truth, hypothesis novelty assessment, biological validation, or formal significance test was used. The benchmark does not demonstrate meaningful scientific discoveries or equivalent discovery quality. Candidate counts and choice probabilities are not validated research findings.

The engine currently expresses candidates through categorical choices and template-based titles. Developing a specific, falsifiable research question and deciding whether its evidence is meaningful require a subsequent review. Jev API computing time and live output quality are unmeasured.

## Protocol

- Measurement date: 2026-10-02. Hardware: NVIDIA GB10, aarch64, NVIDIA driver 580.159.03.
- Qwen: local Ollama `qwen3.6:35b`, Q4_K_M; model metadata reports 36.0B parameters. GPU loading was verified from **42/42 layers offloaded** and an active CUDA compute process.
- Laya: multilingual checkpoint on CUDA, revision recorded in [latency-results.json](latency-results.json); no CPU fallback was observed.
- One request ran at a time. Qwen ran while Laya was stopped; Laya ran after Qwen was unloaded. Provider order was fixed, with requests shuffled within each pass.
- Both models received the same complete evidence, question definitions, and choices. No truncation or reduction of the required questions was accepted.
- Time runs from HTTP request start through answer validation. Laya tokenizer checks are included. Qwen generates choice IDs; Laya also returns probabilities. Free-text hypothesis writing and Qwen probability generation were not measured.
- Qwen settings: `think=false`, temperature 0, seed `20261002`, context 32,768, maximum output 2,048 tokens. The request required all question IDs in a JSON object.
- Startup and warmup were excluded. One sampled payload was used for warmup, so the first pass is not strictly an uncached evaluation. The engine answer cache was unused; native server caches were allowed.

## Records and reproduction

[latency-results.json](latency-results.json) contains model metadata, hardware checks, anonymous sample ordinals, measured times, and aggregate agreement. It omits source evidence, study identifiers, input hashes, dataset dimensions, and raw model answers. Private local receipts retain the original evidence bindings used to compute these aggregates.

To reproduce the caption-free English figure:

```bash
python -m pip install -e '.[plots]'
python scripts/plot_latency.py
```

Optional Korean axis labels:

```bash
python scripts/plot_latency.py --lang ko --font /path/to/Korean-font.otf --out /path/to/latency-ko.png
```

To make a new local timing sample using your own frozen run:

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

The GPU script explicitly stops/starts the named local containers, verifies GPU use, unloads Qwen, and restores Laya on exit. Adjust the container arguments for your installation. Keep these raw local run folders private; the benchmark scripts retain source evidence and native responses there. The public JSON is a reduced aggregate export, not an unfiltered run artifact.
