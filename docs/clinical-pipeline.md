# Clinical-question discovery (v0.2)

**English** | [한국어](clinical-pipeline.ko.md)

New meta-analysis profiles use clinical mode by default. Existing frozen runs must use their saved source; create a new run to adopt this version. `clinical.enabled: false` retains the legacy row/operator export for reproducibility. DEG behavior is unchanged.

The sequence is **ledger linkage → confirmed terminology normalization → clinical questions → dependency assessment → exhaustive Laya/Jev inspection → question-family CSV**. Every row is still inspected, including incomplete, contextual, held and blocked evidence. No count or rank removes a model inspection.

## Run the synthetic example

```bash
python -m bio_topics plan --input examples/meta-clinical.csv --profile profiles/meta.clinical.example.yaml --out runs/clinical-example
python -m bio_topics run --out runs/clinical-example
python -m bio_topics verify --out runs/clinical-example
```

The Laya example uses the existing local server. The Jev equivalent is `profiles/meta.clinical.jev.example.yaml`; explicitly authorize external evidence transfer with `run --allow-external`. Do not copy synthetic populations, drugs, overlap declarations or analysis definitions into a real project.

## Ledger linkage

`clinical.ledger` accepts lists of `publications`, `studies`, `populations`, `analyses`, and `effects`. Each entry requires `id`, `fields`, `confirmed` (boolean), and `source_reference`. Lookup uses exact mapped `publication_id`, `study_id`, `population_id`, `analysis_id`, or `source_effect_id` respectively. Links are followed from effects to analyses to populations to studies to publications. Many effects may cite one analysis; papers and populations are not treated as interchangeable identities.

`clinical.ledger_files` loads mapped CSV, TSV or XLSX ledgers. Paths are relative to the profile. See the example profile for `entity`, `path`, `id_column`, `columns`, `confirmed`, `source_reference`, and optional `sheet`. The plan embeds materialized entries, freezes copies under `ledger_inputs/`, and verifies their hashes. Changing the original external file does not alter an existing run.

Inheritance is scope-limited: publications supply bibliographic fields; studies supply design/data source/country; populations supply participant attributes and cohort IDs; analyses/effects supply clinical attributes and explicit parent identities. An entire paper cannot supply a treatment timing or comparator to all its estimates. Effect values, uncertainty, approvals and source-block flags are never inherited from this metadata ledger. Explicitly map them from the effect table.

Original input, parsed `original_fields`, provenance, proposal entries, confirmed links, conflicts and normalization events are retained in `records.json` and `clinical-audit.json`. Conflicting confirmed attributes become unresolved in canonical fields while both source values remain in provenance. Unconfirmed entries are proposals only. There is no fuzzy title matching or automatic DOI lookup.

## Terminology and question boundaries

For each field, `clinical.normalization` contains rules with `canonical`, `aliases`, `confirmed` and `source_reference`. Only confirmed aliases change canonical fields. Unicode/case/whitespace matching applies within the explicitly supplied alias list. Conflicting mappings are rejected. There is no OR/RR/HR conversion and no inference of missing scientific attributes.

A complete question requires population, treatment stage, drug class, drug definition, exposure timing, comparator type and definition, outcome definition and outcome time. Optional subgroup/start/updating fields also distinguish questions. `clinical.question_fields` adds required dimensions; it cannot remove the core boundaries. Missing required meanings and linkage conflicts isolate the row into an unresolved question, even when other rows have the same missing fields. Explicit researcher declarations such as `not_applicable` may be used when justified.

Analysis partitions further retain estimand, time origin, design, measure, unit, model, adjustment, dose, lag and duration, plus `clinical.analysis_fields`. Different models can remain under one question while being kept distinct for synthesis. `inspection.pairs: within_questions` inspects every pair inside each resulting question, including cross-publication pairs. `all`, `within_groups` with explicit `pair_group_by`, and `none` remain explicit alternatives. Clinical cells use question IDs; `cell_fields` remains required by the common profile schema but does not override clinical boundaries.

Set `analysis_role: context` for contextual descriptors; they remain inspected and can be linked to a complete question, but receive no effect-evidence bonus. Supported comparative measures default to `effect`; other unspecified roles remain `unresolved`. No role is guessed from a model response.

## Dependence and counts

Prefer `population_id` identifying the actual participant sample. Without it, a single explicitly mapped cohort ID supplies identity; multiple cohort IDs in one estimate are a combined, unresolved unit, never multiple independent contributions. A study ID alone does not establish participant independence.

`clinical.cohort_relations` entries require `left`, `right`, `relation`, `confirmed`, and `source_reference`; an optional `question_scope` limits applicability by exact canonical attributes. Endpoints are `population:ID` (when population_id is present) or `cohort:ID` (otherwise). Relations are `same`, `partial_overlap`, `contains` (left contains right), `disjoint`, or `unknown`. Use participant-sample IDs to distinguish periods/subsets within a broad cohort. Different population IDs are not automatically disjoint, even within one paper.

Confirmed `same` identities collapse transitively, including declared intermediate identities absent from the candidate. Partial overlap and containment are preserved as directed/source-backed relations and conservatively connect dependency groups; they do not collapse participant identities or become independent replications. Conflicting overlap declarations are flagged. Independence is reported only when every distinct cited effect population has explicit identity and every pair of identity groups has a confirmed disjoint relation. Otherwise the CSV count is blank (`null` in JSON), with `independence_status: unresolved`. This conservative policy does not estimate an effective sample size or solve partial-overlap covariance.

| Column | Meaning |
| --- | --- |
| `paper_count` | Distinct cited publication IDs only; no study-ID proxy |
| `unique_study_count` | Distinct cited study IDs |
| `missing_paper_identity_rows` | Rows awaiting publication linkage |
| `cohort_count`, `population_count` | Declared cohort IDs and resolved participant-unit identities |
| `known_dependency_group_count` | Components connected by known overlap; not a count of independent replications |
| `independent_evidence_count` | Confirmed mutually independent cited effect units; blank when unresolved |
| `unresolved_independence_count` | Identity groups lacking sufficient evidence to establish independence |
| `eligible_evidence_count` | Units with complete question attributes, valid supported effect points, no linkage conflict, and no held/blocked source |
| `eligible_independent_evidence_count` | Independence assessed for eligible units; blank when unresolved |
| `eligible_paper_count` | Distinct publication IDs contributing eligible effect evidence |

Eligibility here is for discovery ranking. It does **not** grant synthesis approval, verify CI construction, or establish scientific validity. Synthesis additionally requires approval, compatible analysis partitions, valid uncertainty and confirmed eligible independence. One estimate is selected per confirmed population identity; unresolved overlap blocks synthesis and is reported at preflight. Complex covariance modeling is not implemented.

## Ranking and deliverables

Within each route/operator bucket, complete questions, metadata ready for review, and eligible evidence take precedence. The remaining ordering uses:

```text
evidence_score = paper_count_weight × log2(1 + eligible_paper_count)
               + independent_evidence_weight × log2(1 + eligible_independent_evidence_count)
```

Defaults are 0.25 and 0.5, each configurable from 0 to 1. Unresolved independent counts contribute zero to that term. Additional papers from the same population can increase only the publication term. Counts are recomputed from the unique union of cited rows after aggregation; repeated model decisions do not inflate them. Round-robin diversity across route/operator buckets is retained. The score is a priority convention, not a statistical significance test, a calibrated probability, or a validated research-quality measure.

- `candidates.csv` / `candidates.jsonl`: families grouped by clinical question set, operator, focus and execution route. They retain every member inspection ID and source row. Cross-question comparisons remain identifiable as a set of questions. Distinct analysis partitions are listed.
- `inspection_results.csv`: **every planned job**, including background, failed and pending decisions, with zero or more candidate IDs. `decisions.jsonl` retains complete receipts.
- `clinical-audit.json`: field-level linkage/normalization history and declared overlap relations.

Structured CSV cells, including lists of IDs, use JSON; UTF-8 BOM supports Korean spreadsheet readers. Blank independence counts mean unknown, not zero. Both CSVs carry inspection and verification status.

Current Laya/Jev classification uses fixed operators and question templates. Families are not asserted to be distinct novel hypotheses: variant-specific judgments are preserved for subsequent scientific review. Falsification, literature novelty, counter-evidence assessment and human acceptance remain explicitly pending. Oversized evidence is rejected rather than truncated; automatic long-card splitting remains unsupported.
