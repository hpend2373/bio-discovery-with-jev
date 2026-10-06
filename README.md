# Bio Topic Discovery with Jev


**v0.3 clinical-question mode:** [ledger configuration, dependency rules and CSV outputs](docs/clinical-pipeline.md). Candidate families and exhaustive inspection records are separate deliverables.
**English** | [한국어](README.ko.md)

A research skill for inspecting every declared unit in DEG/omics result tables or meta-analysis ledgers with **local Laya** or the **TypeSafe Jev API**. It preserves evidence links, records model decisions, and verifies inspection coverage before reporting follow-up candidates.

The current engine uses categorical decisions and template-based candidate titles. Candidates need scientific review, literature checks, and concrete hypothesis development before adoption.

## v0.4: evidence paging and ledger linkage

Enable `inspection.partition_long_evidence: true` for lossless, preflighted pages. Use `link-ledger` for exact effect-ID joins with complete coverage checks. [Guide](docs/long-evidence.md). Page completion does not imply one global full-context judgment.

## Computing time and what the results mean

![Measured GPU request time](docs/evaluation/latency-comparison.png)

Both models ran separately on the same NVIDIA GB10 GPU. Each evaluated the same 30 evidence payloads twice, with 16 categorical questions per request.

| Model | Valid requests | Total measured request time |
|---|---:|---:|
| Laya multilingual · GPU | 60/60 | 45.07 s |
| Qwen3.6 35B · GPU | 60/60 | 251.84 s |

Qwen took **5.59× as long as Laya** in this sample: a difference of **206.77 seconds**. All 960 required choices per model passed completeness and allowed-choice checks. **Paired choice agreement was 26.25% (252/960)**; passing the response contract does not establish equivalent judgments.

These measurements support faster categorical inspection in this configuration. They do not establish scientific validity, novelty, equal discovery quality, or statistical significance. No expert ground truth or formal significance test was used. Jev was not timed.

[Protocol, interpretation, and timing records](docs/evaluation/LATENCY.md) · [한국어](docs/evaluation/LATENCY.ko.md)

## Install

Python 3.10 or later:

```bash
git clone https://github.com/hpend2373/bio-topic-discovery.git
cd bio-topic-discovery
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Local Laya

Use an existing Laya server and a Docker-accessible tokenizer from the same model revision. Configure `backend.url`, `container`, and `model_path` for your installation. Normal discovery commands reuse the server.

```bash
bio-topics plan --input examples/meta-clinical.csv --profile profiles/meta.clinical.example.yaml --out runs/meta-laya
bio-topics run --out runs/meta-laya
bio-topics verify --out runs/meta-laya
```

### Jev API

Set `TYPESAFE_API_KEY` and choose a pinned model version. `--allow-external` explicitly permits sending the input evidence to the TypeSafe API.

```bash
export TYPESAFE_API_KEY="YOUR_KEY"
bio-topics plan --input examples/meta-clinical.csv --profile profiles/meta.clinical.jev.example.yaml --out runs/meta-jev
bio-topics run --out runs/meta-jev --allow-external
bio-topics verify --out runs/meta-jev
```

For DEG inputs, use `examples/deg.csv` and `profiles/deg.example.yaml` or `profiles/deg.jev.example.yaml`. Examples are synthetic. For your own data, adapt the column mapping, question, declarations, and inspection scope; set `synthetic_example: false`.

[Backend configuration](docs/backends.md) · [한국어](docs/backends.ko.md)

## Codex skill

After installing the engine, copy the portable skill into your Codex skills directory:

```bash
cp -R skills/bio-topic-discovery ~/.codex/skills/
python skills/bio-topic-discovery/scripts/run.py --project "$PWD" --help
```

The launcher locates the repository or the installed `bio_topics` package. Use `--project PATH` or `BIO_TOPIC_DISCOVERY_ROOT` for a different installation. The skill can respond in English or Korean; current engine-generated report files use Korean.

## Exhaustive inspection contract

```text
CSV/Excel → mapping and preserved source values → deterministic facts
          → every declared row, cell, pair and supported scenario → Laya / Jev
          → recorded model responses → coverage verification → follow-up candidates
          → scientific review and human decisions
```

- No FDR, top-K, score, or time cutoff removes declared inspection units.
- Declare pair scope as `all`, `within_groups`, or `none` before execution. Exhaustive coverage applies to that declared scope.
- Weak, held, and blocked evidence remains in inspection; synthesis approval is tracked separately.
- Resume only with matching inputs, profile, code, model, and tokenizer. Changed backends require a new run.
- Missing, failed, or truncated model responses remain incomplete. Synthetic test responses do not prove real model coverage.
- Completion of inspection does not imply completion of every possible analysis or scientific validation.

## Outputs and supported scope

**`candidates.csv` is the primary deliverable.** Each row is a candidate or an item requiring additional confirmation, with its question, evidence links, observations, limitations, falsification note, required checks, model judgment, and inspection/verification status. All candidates are retained. `run` writes the CSV automatically and returns its absolute path as `candidate_csv`.

```bash
# Regenerate the CSV from a verified run, without another model call.
bio-topics report --out runs/YOUR_RUN
```

The CSV uses English field names and UTF-8 with BOM for spreadsheet compatibility; current generated questions use Korean. Structured evidence cells contain JSON. [CSV field guide](docs/candidate-csv.md) · [한국어](docs/candidate-csv.ko.md).

`REPORT.ko.md` and `candidates.jsonl` are supporting outputs. Full decision records remain in `decisions.jsonl` and `inspection.sqlite3`; `verify` checks response completeness and evidence bindings.

Inputs include CSV/TSV/XLSX. The engine supports DEG evidence, meta-analysis evidence, declared comparisons, and limited compatible inverse-variance synthesis. Meta-regression, diagnostic-accuracy joint synthesis, complex covariance models, and automatic splitting of long evidence cards are not implemented. Unknown scientific metadata stays unknown.

Laya returns choice probabilities, which are not probabilities that a hypothesis is scientifically true. Jev request/response contracts have mock tests; live Jev execution and performance remain unverified.

## Development

```bash
python -m unittest discover -s tests -v
```

Contract tests use synthetic fixtures. Scientific validation requires independent review and evidence beyond software checks.

## Official references

- [TypeSafe API](https://docs.typesafe.ai/api) and [model versions](https://docs.typesafe.ai/models)
- [Laya repository](https://github.com/ConvaiInnovations/laya)

v0.3 meta-analysis links ledgers, normalizes confirmed terminology and exports clinical-question families. Questions have declared upper-question, stratum and sensitivity levels. Independence belongs to selected analysis sets, with blank unresolved counts. Publication credit defaults to zero and is capped for repeated publications. `analysis_sets.csv` records selected effects, overlap and review gates; `candidate_effects.csv` links all same-question effects and roles. Model completion does not certify source checks, dual review, outcome RoB or synthesis approval. See the [clinical pipeline](docs/clinical-pipeline.md).

## v0.4.1 inspection and output updates

- Set `inspection.compact_evidence: true` to use reversible tables and shared provenance references. Every original value is retained and checked by round-trip reconstruction; operator questions and declared inspection scope stay intact. Oversized tables are expanded before lossless paging.
- An explicit unresolved diagnosis/timing review clears an inherited exposure-timing label. The original label and review evidence remain in provenance. This does not infer a replacement window or certify the source.
- Exact ID linkage and metadata completeness are reported separately. Population descriptions stay descriptions; they do not establish participant identity or independence.
- In clinical mode, `candidates.csv` contains families with complete question metadata, `review_queue.csv` holds incomplete families, and `all_candidate_families.csv` preserves every family. `candidate_effects.csv` links families in both files; `inspection_results.csv` retains all inspections. Complete question metadata does not establish synthesis eligibility.
- Changed scientific inputs require new inspections. Existing completed runs keep their frozen code and inputs. This release does not provide automatic cross-run reuse of model receipts.

The 69 synthetic software tests pass. These checks cover implementation contracts and do not establish scientific validity or live Jev performance.
