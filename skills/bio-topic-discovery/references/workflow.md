# Runs and profiles

**English** | [한국어](workflow.ko.md)

See the repository `README.md` and `profiles/deg.example.yaml` / `profiles/meta.example.yaml` for supported fields. Examples are synthetic; set `synthetic_example: false` for real evidence.

```bash
python3 scripts/run.py plan --input /absolute/data.csv --profile /absolute/study.yaml --out /absolute/new-run
python3 scripts/run.py run --out /absolute/new-run
python3 scripts/run.py verify --out /absolute/new-run
python3 scripts/run.py status --out /absolute/new-run
```

Profiles require `schema_version: 1`, `domain: deg|meta`, `question`, `columns`, and `inspection`. `columns` maps common field names to source columns. DEG requires `entity_id` and `comparison`; map log2fc/FDR when available. Meta-analysis requires `study_id`, `measure`, and `value`. Use researcher-confirmed `declarations` for scientific attributes absent from the source.

`inspection.cell_fields` partitions all rows into comparison cells. Declare `pairs: all|within_groups|none`; `within_groups` requires `pair_group_by`. Choose scientific scope intentionally, such as cross-cell pairs for matching genes/comparisons or study pairs within an outcome family. `all` evaluates every n(n−1)/2 pair. Explain scope and cost at planning time.

Default operators are `integrity`, `heterogeneity`, `robustness`, `bias`, `gap`, `generalizability`, `contradiction`, and `decision`. Enable `mechanism` only with sourced `knowledge_relations`. Provide source/target/type/source_reference and distinguish biological facts from assumptions.

Synthesis requires explicit activation in a meta profile. Express CI levels between 0 and 1, such as 0.95. For reported SE, declare `se_scale: log` for ratio measures or `identity` for differences. Reconstruct SE from a CI only with confirmed `ci_method: wald` and `ci_distribution: normal`. Check `source_blocked`, `hold_reason`, `synthesis_approved`, and required metadata. Split cells or disable synthesis when estimands or adjustment definitions are incompatible, even if scales match.

New run directories contain frozen input, `profile.json`, `records.json`, a code snapshot, and `inspection.sqlite3`. A failed `.planning` directory is not a completed run. Resume changed-code runs using their original source snapshot or create a new plan. Do not modify inputs/profiles to force a resume match.

Use `run --retry-failed` only after resolving causes. Check `verification.json` and individual errors. Do not change model weights, servers, or containers without authorization. Local tokenizer verification needs read/execute access to the configured container.

Primary deliverable: `candidates.csv`. It retains every candidate with source links, observations, limits, falsification/confirmation fields, and inspection/verification status. Deliver an absolute file link in the final answer. The run response returns `candidate_csv`; `report --out PATH` regenerates exports only after verification. Structured cells are JSON, record IDs are separated by semicolons, and UTF-8 BOM supports spreadsheet readers. A header-only file means no selected candidates; check `candidate-summary.json` and verification before interpreting it.

Supporting files: `REPORT.ko.md`, `candidates.jsonl`, `decisions.jsonl`, `verification.json`, and `SYSTEM2-REVIEW.ko.md`. Verification binds actual responses to every planned task. A choice probability is not a scientific truth probability.

Meta-analysis ranking uses a default paper-count weight of 0.25. Configure `ranking.paper_count_weight` (0–1) in a new profile; see `docs/candidate-csv.md` for the formula, dependency/eligibility rules and CSV fields. This changes post-inspection ordering only.

## v0.3 clinical questions and analysis sets

Read `profiles/meta.clinical.example.yaml` and the engine's `docs/clinical-pipeline.md`. Declare hierarchy with `clinical.partition`, outcome-blind selection rules with `clinical.analysis_sets`, and origin provenance with `clinical.question_registry`. Link scoped metadata through `clinical.ledger_files`. Review selected effects, overlap policy, evidence levels and unresolved relationships in every analysis set; verify that candidate-effect links retain opposing and null results. Source checks, dual review, outcome RoB and synthesis approval are independent gates. Publication bonus defaults to zero with a repeated-publication cap. The old schema/scoring above is for `clinical.enabled: false` reproducibility. Structured lists in new clinical CSV files use JSON.
