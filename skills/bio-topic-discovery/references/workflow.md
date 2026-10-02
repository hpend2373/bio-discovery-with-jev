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

Final files include `REPORT.ko.md`, `candidates.csv`, `candidates.jsonl`, `decisions.jsonl`, `verification.json`, and `SYSTEM2-REVIEW.ko.md`. Verification checks that actual responses bind to every planned task. A candidate's choice probability is not the probability that its hypothesis is true.
