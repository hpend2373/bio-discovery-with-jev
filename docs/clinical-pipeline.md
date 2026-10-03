# Clinical-question discovery (v0.3)

**English** | [한국어](clinical-pipeline.ko.md)

The pipeline links metadata ledgers, applies confirmed terminology mappings, builds a declared question hierarchy, enumerates analysis sets, and asks Laya/Jev to inspect every planned row, question cell, pair and analysis set. It does not infer source verification, independent dual review, outcome risk of bias (RoB), synthesis approval or scientific truth from model completion.

## Start and migrate

```bash
python -m bio_topics plan --input examples/meta-clinical.csv --profile profiles/meta.clinical.example.yaml --out runs/clinical-example
python -m bio_topics run --out runs/clinical-example
python -m bio_topics verify --out runs/clinical-example
```

Use the existing local Laya server. `profiles/meta.clinical.jev.example.yaml` supports Jev with explicit `run --allow-external` authorization. Examples are synthetic; their scientific definitions must not be copied into real data. Create a new run for changed code or policy. Frozen old runs remain reproducible with their saved source. `clinical.enabled: false` retains the old export; DEG behavior is unchanged.

In v0.3 replace `clinical.question_fields` / `analysis_fields` with `clinical.partition`. Remove `ranking.independent_evidence_weight`: independence is a review-priority tier, not an additive publication bonus. Old fields raise a migration error instead of silently changing meaning.

## Link and normalize evidence

`clinical.ledger` accepts `publications`, `studies`, `populations`, `analyses` and `effects`. Entries require `id`, `fields`, `confirmed`, `source_reference`. Exact mapped `source_effect_id → analysis_id → population_id → study_id → publication_id` links supply metadata only at its declared scope. Publication entries supply bibliography, not a drug or comparator to every estimate. Values, CIs, review states and approval flags are mapped directly from effect rows, not inherited from a general metadata ledger.

`clinical.ledger_files` reads CSV, TSV or XLSX using `entity`, `path`, `id_column`, `columns`, `confirmed`, `source_reference` and optional `sheet`; paths are relative to the profile. Materialized entries and original file copies/hashes are frozen. Unconfirmed links stay proposals. Conflicting confirmed values remain in provenance and become unresolved in canonical fields. `clinical.normalization` uses confirmed, sourced `canonical` / `aliases` rules only. No fuzzy linkage, missing-value imputation or effect-measure conversion is performed.

## Declare three levels

The default upper-question identity uses **drug class, exposure timing and outcome definition**. Population/treatment stage form strata. Comparator, model, lag, dose, follow-up and other variations remain below the question. A different model or follow-up does not itself create a new upper question.

```yaml
clinical:
  partition:
    question: [exposure_class, exposure_timing, outcome_definition]
    stratum: [population, treatment_stage]
    sensitivity: [exposure_definition, comparator_type, comparator_definition,
                  outcome_time, model, lag, dose, exposure_duration]
```

Each clinical attribute can appear in one declared level; users can move an attribute when scientifically justified. The full default is in the example profile. Missing upper-question meanings isolate unresolved questions; missing stratum details do not split the upper question but block selection for that stratum. Basic synthesis compatibility (including measure, estimand, time origin, exposure/comparator/outcome definitions and population) remains in the analysis signature even if omitted from the hierarchy. This prevents an omitted field from silently authorizing incompatible pooling.

Every exact compatible metadata variant becomes an analysis group under its stratum. Different groups are visible as sensitivity alternatives, not prematurely pooled. `pairs: within_questions` inspects every pair in each upper question, including cross-stratum differences; it does not authorize cross-stratum synthesis. `all`, `within_groups` with explicit `pair_group_by`, or `none` remain declared alternatives. There is no top-K or post-result pair filtering.

## Analysis sets and independence

`analysis_sets.csv` is the authority for independent counts. Every set records its selected **record IDs and source effect IDs**, available rows, exact selection rule, overlap policy, supporting independence evidence, unresolved relations, selected-unit count and usable independent-unit count. An unresolved independent count is blank (`null` in JSON), never relabeled zero. An empty selected set has zero units and an explicit exclusion reason.

Prefer an actual participant-sample `population_id`; otherwise one declared `cohort_id` supplies identity. Multiple cohorts in one combined estimate remain unresolved. Study or publication IDs do not establish independence. Relations use `population:ID` or `cohort:ID` endpoints, `same`, `partial_overlap`, `contains` (left contains right), `disjoint` or `unknown`, plus `confirmed`, `source_reference`, `evidence_level`, and `rationale`. An optional exact `question_scope` restricts applicability using canonical fields.

| Evidence level | Interpretation |
| --- | --- |
| `participant_linkage` | Documented direct participant linkage/comparison |
| `documented_sampling` | Documented institutions, periods and eligibility establish the sampling relationship; participant IDs are not required |
| `author_confirmation` | A cited author confirmation establishes the relationship |
| `inferred_design` | A plausible design-based inference; does not establish independence |
| `unspecified` | No adequate evidence level supplied; remains unresolved |

The first three are accepted by default; `clinical.independence_policy.accepted_levels` can restrict them. A confirmed flag alone, without an accepted evidence level and rationale, cannot certify independence. These are supplied, sourced judgments, not automatically authenticated by the model.

Confirmed identical identities collapse transitively. Direct known overlaps prohibit selecting both estimates. The engine enumerates **all maximal sets without known pairwise overlap**, without choosing by result direction or significance. If A overlaps B and B overlaps C, but A and C are disjoint, sets `{A,C}` and `{B}` are both retained. Unknown relationships do not vanish: a selected set with unresolved independence remains unresolved and cannot be synthesized. This is an alternative-estimate policy, not a covariance model.

The exhaustive exploratory set is always retained. Optional `clinical.analysis_sets` rules declare primary candidates or named alternatives:

```yaml
clinical:
  analysis_sets:
    - id: protocol_adjusted
      role: primary_candidate
      where: {model: adjusted}
      selection_timing: before_data_review
      source_reference: protocol_section_4
      reason: Prespecified adjustment definition
```

Roles are `primary_candidate`, `alternative_model`, or `sensitivity`. Selectors accept exact clinical metadata only. Selecting by effect value, p value, CI, sign, significance or SE is rejected. Declared rules never remove the other exploratory alternatives, and a primary candidate is not automatically a final adopted estimate.

## Provenance of the question

Unregistered discovered questions default to `posthoc_exploratory`. `clinical.question_registry` distinguishes `protocol`, `posthoc_exploratory` and `validation_hypothesis`. Each entry requires an ID, exact upper-question `scope`, `origin`, `source_reference`, `created_at`, and `before_data_review`; validation questions may cite a `parent_question_id`. Protocol origin requires a declaration that it preceded data review. The declaration is marked as user-supplied, not independently verified.

A registry entry describes the underlying question. New hypotheses generated from inspecting its results still carry `generated_hypothesis_origin: posthoc_exploratory`. Opposing, null, favorable and background-classified rows under the same question all appear in `candidate_effects.csv`, including held rows with explicit reasons.

## Review priority, not synthesis weight or certainty

Within comparable route/operator/precision groups, order is:

1. Upper-question completeness and usable analysis sets.
2. Independent units and comparable precision in the analysis sets.
3. Outcome-specific RoB.
4. Data completeness.
5. Optional capped publication credit.

The priority uses a **conservative envelope over all nonempty declared analysis sets**: minimum confirmed independent count, minimum comparable precision, worst assessed RoB (unknown is explicitly separate), and minimum completeness. It does not select a favorable representative estimate. Precision is descriptive inverse-variance information only when all selected effects have valid uncertainty, confirmed independence and one common measure/unit/estimand/time-origin/outcome/stratum signature. Incomparable precision stays blank; global presentation preserves diversity between groups.

`paper_count` still displays distinct publication IDs, without a study-ID proxy. The publication bonus defaults to **0**. If `ranking.paper_count_weight` is enabled (0–1), it uses at most one credit per confirmed selected participant identity, and zero when independence is unresolved. The candidate uses the minimum scenario credit. Five repeated publications from one cohort cannot earn five credits. The optional final tiebreaker is `weight × log2(1 + credit)`. `ranking_score` contains only this tiebreaker, not the entire lexicographic order. Priority fields are never passed as pooling weights or certainty ratings.

## Separate review gates

All states below come from explicit effect-row evidence, not model probabilities or coverage:

| Gate | Required input |
| --- | --- |
| Original-source verification | `source_verification_status: full_text_verified` and `source_verification_reference` |
| Independent dual review recorded | `dual_review_status: agreed`, at least two distinct `reviewer_ids` (semicolon-delimited in CSV), and `dual_review_reference` |
| Outcome RoB | `rob_status: assessed`, `rob_judgment: low|some_concerns|high`, `rob_tool`, `rob_source_reference`, and matching `rob_outcome_definition` |
| Synthesis approval | Explicit `synthesis_approved: true` |

A set is `synthesis_ready` only when all selected rows pass these gates, uncertainty/compatibility checks, and set-specific independence checks. Explicit `synthesis.enabled` is still required to calculate a synthesis. Readiness is not a claim that synthesis has run. A high RoB judgment is retained and affects review priority; it is not silently converted to low risk. Partial-overlap covariance modeling, source retrieval, actual dual review and automated RoB adjudication are not implemented.

## Deliverables

| File | Purpose |
| --- | --- |
| `candidates.csv` | Upper-question/operator/focus/route families, origin, strata, analysis-set links, raw publication counts and review priority |
| `inspection_results.csv` | Every planned job, including background, failed and pending jobs, and candidate links |
| `analysis_sets.csv` / `.jsonl` | Exact selected effects, overlap handling, per-set independence, precision, gates and exclusions |
| `candidate_effects.csv` | Candidate–effect–set links with `primary_candidate`, `alternative_model`, `sensitivity`, `background`, or `held` roles |
| `clinical-audit.json`, `records.json` | Raw evidence, scoped linkage, conflicts, normalization history and hierarchy |

Structured CSV cells use JSON and UTF-8 BOM. Candidate families remain template-based follow-up proposals; distinct hypotheses, literature novelty, concrete falsification plans and human acceptance require subsequent scientific review. Oversized model input fails rather than being truncated. Verification checks native responses for every declared unit; it does not certify scientific validity. Historical latency charts do not benchmark this expanded v0.3 pipeline.
