# Changelog

**English** | [한국어](CHANGELOG.ko.md)

## 0.5.0 — 2026-10-08

**CellChat compatibility; experimental research software.** This is the first tagged GitHub release. Earlier versions below describe documented development milestones, not retrospectively published releases.

### Added

- Dedicated `bio-topics cellchat plan/run/verify/status` workflow for CellChat v1/v2 group-level LR CSVs and pathway CSVs.
- R export helper for complete stored `net` arrays, including zero and non-significant entries, complex/cofactor annotations, contexts and model parameters. The importer checks declared tensor axes and row counts.
- Complete directed-edge cards with applicable questions, exact-request cache/checkpoints, source and response bindings, and a stop after three consecutive failures.
- Candidate families in `candidates.csv`, source links in `candidate_evidence.csv`, all judgments in `inspection_results.csv`, and coverage verification.
- English/Korean CellChat guides, portable skill instructions, a synthetic example, profile and 12 CellChat contract tests.

### Interpretation and limitations

- Provided-row CSV coverage and full stored-tensor coverage are distinct. Missing edges are unknown. Upstream filtering cannot be reversed.
- Inferred communication strength and permutation p-values are not DEG effects/FDR, between-condition tests, causal evidence or metabolic flux. Model probabilities do not establish scientific validity.
- Condition comparisons require an explicitly declared comparable analysis group and remain descriptive. Independent patient replication is not inferred from repeated rows or pooled objects.
- Native Spatial CellChat v3 objects, automatic DEG–CellChat joins, patient-level differential communication tests, automatic long-card splitting/global integration and multi-card CellChat GPU batching are not implemented.
- The R helper has not been executed here because R is unavailable. Live Jev API execution is unverified. Local Laya was tested using a small synthetic CSV (4 original rows, 3 cards, 3 valid native judgments, no reported truncation).
- The public release tree passes **83 Python tests**, including 12 CellChat tests. Local-only experimental tests are excluded from this release total.
- The 12 CellChat tests cover source preservation, zeros/missingness, direction, complexes, tensor completeness, duplicate observations, patient context and response contracts. Synthetic tests and transport checks do not establish biological validity.

### Upgrade and reproduce

Install or update the engine from the `v0.5.0` tag and refresh the installed skill from `skills/bio-topic-discovery`. No automatic rerun, data migration or server restart is performed. Plan changed inputs or scientific rules in a new run directory.

Existing runs bind the exact engine source hash. Resume or verify them with their saved `source/bio_topics` snapshot; even a package-version change affects that fingerprint. Preserve their inputs, profile, model revision and tokenizer. Do not edit a frozen run to make it match a new release.

The package version in `pyproject.toml` and `bio_topics.__version__` is `0.5.0`. This is the **discovery pipeline version**, separate from the Laya/Jev model version, CellChat/CellChatDB version and each run's scientific contract.

## 0.4.2 — documented development milestone

Evidence-sharing inspection became the default skill design. New historical DEG row/cell/pair plans require explicit `--legacy-deg`. The public milestone defined generic gene-card execution, dependency-aware reuse and multi-card batching as implementation requirements; it did not certify their completion. See [the design guide](docs/efficient-inspection.md).

## 0.4.1 — documented development milestone

Reversible compact evidence, reviewed timing-conflict handling, separate incomplete-question review queues, and clearer source linkage/completeness boundaries. See the README's v0.4.1 section.

## 0.4 — documented development milestone

Lossless evidence paging and exact effect-ID ledger linkage, with separate local-page and global-judgment semantics. See [long evidence](docs/long-evidence.md).

## 0.3 — documented development milestone

Clinical-question families, compatible analysis sets, overlap/independence declarations, exploratory provenance and candidate-to-effect links. See [clinical pipeline](docs/clinical-pipeline.md).

## Version policy

Use `MAJOR.MINOR.PATCH`. During the experimental `0.x` series, MINOR versions identify new capabilities or deliberate contract changes; PATCH versions identify fixes/documentation without an intended scientific-scope change. Every run still binds exact code and inputs: matching package versions alone never authorize cache reuse or resume. Breaking CLI/schema or judgment changes must be stated in the release notes. Do not reuse old responses merely because the feature has the same name.

GitHub releases identify a fixed tag/commit and state implementation, validation and limitations separately. Experimental releases are marked as pre-releases on GitHub; this label is not a scientific quality rating. Historical milestone dates are omitted where no tagged release exists.
