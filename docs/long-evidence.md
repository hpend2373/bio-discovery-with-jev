# Evidence paging and full ledger linkage (v0.4)

**English** | [한국어](long-evidence.ko.md)

Enable `inspection.partition_long_evidence: true` in a new project profile. `plan` now checks **every execution page before inference**, using the existing Laya tokenizer and serializer. It does not load another model. For explicitly selected Jev, planning checks the declared request byte limit locally; it does not call the API or establish Jev's internal token limit.

## What the coverage contract means

A logical row, question cell, analysis set or declared pair keeps its original identity. If it fits, it is sent intact. If it does not fit, the engine enumerates all original JSON leaf values with typed paths, preserving empty containers, nulls and scalar types. Long strings carry explicit character offsets. Contiguous ranges of these entries are bisected until every page fits. The frozen `partition-plan.json` includes parent and entry hashes, ranges and tokenizer receipts. Verification regenerates the pages from the frozen source and rejects omissions, overlap, reordering or changed values.

Every page receives every declared operator's **own actual model response**. Page judgments are not merged into fabricated probabilities or a synthetic global verdict. A parent is complete only when every page's operator judgments succeed. `partition-coverage.csv` distinguishes parent completion from physical page counts; `inspection_results.csv` includes parent IDs, entry ranges and context modes.

**Reading every page is not the same as jointly reasoning over all evidence in one context.** A candidate remains a review family. Cross-page higher-order interactions and unrestricted all-pairs comparisons are not claimed. The original pair contract is preserved. For a declared pair, every page repeats both endpoints' full normalized fields in a joint table; raw values and provenance remain in the lossless pages. If that mandatory joint table or an indivisible entry itself cannot fit, planning fails explicitly. Source verification, independent dual review, outcome RoB and synthesis approval stay separate.

Old runs must use their frozen source. Create a new run for the new transport; do not edit old manifests to relabel an incomplete run.

## Full effect ledger

Join by explicit effect ID, not publication titles or similarity. The helper recognizes one of `source_effect_id`, `effect_row_id`, or `effect_id`, and explicit canonical/common column names. It fills missing fields only; conflicting supplied values remain conflicts. It preserves the original input cells and freezes the ledger with a hash during planning.

```bash
python3 -m bio_topics link-ledger \
  --input /absolute/input.csv --profile /absolute/project.json \
  --ledger /absolute/full-effects.csv --out /absolute/new-linked-profile
python3 -m bio_topics plan \
  --input /absolute/input.csv --profile /absolute/new-linked-profile/profile.json \
  --out /absolute/new-run
python3 -m bio_topics run --out /absolute/new-run
python3 -m bio_topics verify --out /absolute/new-run
```

The default helper requires a confirmed, conflict-free effect join for **every input row**. `--allow-unmatched` explicitly permits unresolved rows; it does not establish linkage. Duplicate effect IDs fail rather than choosing an arbitrary row. XLSX needs an explicit sheet when there are multiple sheets; formulas are rejected. Use `--ledger-ci-level-percent` only if that ledger explicitly uses percentage CI levels. Units are not inferred from values or inherited from another input file.

`ledger-linkage.csv` records every input/entity lookup, match, source and conflict. `unused-ledger-entries.csv` records ledger entries outside the input; they have **not** been model-inspected. To inspect the entire ledger, use it as the input as well or explicitly add those effects to a new input. Presence of a ledger file is not proof of source verification or of population independence.

Additional studies, populations, analyses and publications are supported through scoped `clinical.ledger_files`; cohort overlap relations still require explicit evidence levels and source references. A publication-level join must never impute effect-specific timing or cohort identity. A missing source ledger cannot be reconstructed from a plotting export by assumption.

## Explicit timing qualifiers

A confirmed normalization rule may include `assign`, restricted to literal `lag`, `exposure_updating`, `exposure_duration`, `exposure_start` and `dose` qualifiers. This keeps such qualifiers outside an upper timing label without inventing a source ledger. Assignments require source references, retain original strings, and turn disagreements with supplied ledger metadata into unresolved conflicts; they never overwrite a conflicting value silently.

## v0.4.1 inspection and output updates

- Set `inspection.compact_evidence: true` to use reversible tables and shared provenance references. Every original value is retained and checked by round-trip reconstruction; operator questions and declared inspection scope stay intact. Oversized tables are expanded before lossless paging.
- An explicit unresolved diagnosis/timing review clears an inherited exposure-timing label. The original label and review evidence remain in provenance. This does not infer a replacement window or certify the source.
- Exact ID linkage and metadata completeness are reported separately. Population descriptions stay descriptions; they do not establish participant identity or independence.
- In clinical mode, `candidates.csv` contains families with complete question metadata, `review_queue.csv` holds incomplete families, and `all_candidate_families.csv` preserves every family. `candidate_effects.csv` links families in both files; `inspection_results.csv` retains all inspections. Complete question metadata does not establish synthesis eligibility.
- Changed scientific inputs require new inspections. Existing completed runs keep their frozen code and inputs. This release does not provide automatic cross-run reuse of model receipts.

The 69 synthetic software tests pass. These checks cover implementation contracts and do not establish scientific validity or live Jev performance.
