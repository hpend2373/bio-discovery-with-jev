# CellChat result inspection

**English** | [한국어](cellchat.ko.md)

CellChat results have a dedicated `bio-topics cellchat` workflow. Existing DEG runs keep their frozen code and inputs. This adapter does not run CellChat from DEG tables or merge communication scores into DEG log fold changes.

## What the official documentation means

Reviewed on 2026-10-08 against [jinworks/CellChat](https://github.com/jinworks/CellChat), its [extraction implementation](https://github.com/jinworks/CellChat/blob/main/R/analysis.R), and [inference implementation](https://github.com/jinworks/CellChat/blob/main/R/modeling.R).

- CellChat infers directed communication using transcriptomic evidence and its interaction database, including complexes and cofactors. CellChatDB v2 includes protein and non-protein signaling.
- `net$prob` and `net$pval` are sender × receiver × interaction arrays. `prob` is an inferred strength; `pval` is a permutation result, not DEG FDR, a differential-condition test, or certainty of real communication.
- `subsetCommunication()` returns a table for a single object and a named list for merged objects. Its default threshold removes non-significant entries and zero scores; raising the threshold does not recover zero-score entries. Absence from that export means unknown.
- `netP$prob` contains pathway aggregates after upstream significance selection. It must stay a pathway-level observation; it is not a ligand–receptor row and has no automatically interchangeable LR p-value.
- The repository points to a separate Spatial CellChat v3 implementation. This adapter supports v1/v2 group-level exports; it does not claim native v3 object compatibility.

## Inputs and coverage

1. Existing CSV: preserve every supplied row and column. Required columns: `source`, `target`, `interaction_name`, `prob`. `pval`, ligand, receptor, complex/cofactor composition, pathway and evidence columns are retained when supplied. Coverage is **provided rows only**, regardless of the CSV filename. For pathway CSVs, set `level: pathway` and use `pathway_name` instead of `interaction_name`.
2. Complete stored arrays: use the R helper below. It includes zero and non-significant entries and records axis labels, expected row counts, parameters and contexts. The Python adapter verifies the tensor grid has no missing/duplicate/foreign edges. Coverage is **all stored entries**, not all biologically possible or pre-filtered interactions.

RDS files are exported in R; Python does not guess their serialization. The R helper is original interoperability code using the documented object slots. It requires `CellChat` and `jsonlite` in the user's R environment.

```r
source("scripts/export_cellchat.R")
# Single objects, a named list, or a merged object are supported.
export_cellchat(list(before = cellchat_before, after = cellchat_after),
                out = "cellchat-export", database_version = "your DB version")
```

Optional `contexts` is a data.frame with exactly one row per exported `dataset_id`. A named single object uses its list name; a merged member uses `object_name/member_name`. Columns: `dataset_id`, `condition`, `patient_id`, `species`, `analysis_group`, `cellchat_version`, `database_version`. Unknown values remain `unknown`. Supply one patient ID only for a patient-specific analysis, never invent IDs for a pooled object. The exporter preserves complex/cofactor components from the object's DB and the current stored parameters; it cannot reconstruct filters already applied.

`analysis_group` is an explicit assertion that datasets are comparable: inspect preprocessing, database, population-size weighting, cell definitions, spatial settings and other parameters before assigning it. Without this declaration, cards remain within their dataset/file. Even with it, model comparisons are descriptive; no patient-level differential test or replication score is manufactured.

## Plan, inspect, verify

Adapt `profiles/cellchat.example.yaml` to the study. All cell directions and supplied rows remain in scope; no FDR/top-K filter is applied.

```bash
bio-topics cellchat plan --input cellchat-export/manifest.json \
  --profile profiles/cellchat.example.yaml --out runs/cellchat-study
# Or --input exported-subsetCommunication.csv
bio-topics cellchat run --out runs/cellchat-study
bio-topics cellchat verify --out runs/cellchat-study
```

Local Laya is the default. For Jev, use `backend: {kind: jev, model: jev-1.13.0}`, set `TYPESAFE_API_KEY`, and explicitly pass `--allow-external` to `cellchat run`. The backend keeps the existing pinned-version and response-contract checks. Live Jev execution is not verified here.

Cards share the complete directed edge evidence, with one applicable follow-up question and an additional condition-comparison question only when declared comparable conditions exist. Unknown edge identities and conflicting contexts are isolated and remain inspectable. Opposite directions, LR versus pathway, species and declared DB/software versions stay distinct. Duplicate rows keep separate source IDs but are not counted as independent evidence.

The run preflights **every full card** before any inference. Oversized cards stop the run for an explicit redesign; automatic splitting/global integration is not implemented for this mode. It uses one request per card with shared questions, not multi-card GPU batching. Exact source evidence, question, code and provider bindings govern checkpoint/cache reuse. Three consecutive failures stop execution; resolve the cause before `--retry-failed`. Changing a frozen run's source, profile or provider requires a new plan; use the saved `source/` snapshot to resume after upgrading the engine.

## Outputs and limitations

- `candidates.csv`: one family per directed edge card, including items needing more data; titles are model-decision templates.
- `candidate_evidence.csv`: candidate to original CSV record ordinal and exact row hash. Ordinals include the header; quoted multiline fields may span more physical lines.
- `inspection_results.csv`: all model choices, including background.
- `row-card-links.csv`, `sources.json`, frozen inputs/profile/code, raw receipts and `verification.json`: coverage and provenance.

Partial exports explicitly carry `inspection_status=incomplete_or_invalid`. `verified` means all declared cards passed native response and provenance checks, not biological validation. The adapter does not yet join separate DEG datasets, perform patient-level differential communication statistics, or validate CellChat's upstream inference.

Validation: synthetic Python invariants cover zeros/missingness, direction, complexes, duplicate rows, partial exports, tensor completeness, patient context, source tampering and native-response binding. A small synthetic CSV is also checked against the existing GPU Laya server. The R helper has not been executed in this environment (R is unavailable); validate its exported manifest before using a real object. No private study data are included in these examples.
