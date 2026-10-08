# Evidence-first exhaustive inspection

**English** | [한국어](efficient-inspection.ko.md)

This is the default design policy for new discovery work with Bio Discovery with Jev. Preserve the user's scientific scope and every original observation while reducing repeated representations and redundant questions. It applies to local Laya and explicitly selected Jev. It does not authorize starting or resuming a stopped run.

## Implementation boundary

The skill follows this policy now. The CLI requires `plan --legacy-deg` before it will create a new DEG plan using the existing row/cell/pair × operator executor. That option is for an explicitly chosen historical contract; do not silently add it to bypass this policy. Existing frozen runs and meta-analysis plans retain their contracts.

**The general gene-card executor, dependency-aware cross-run reuse and multi-card GPU batching are design requirements, not completed features of this release.** The existing engine batches questions for one evidence unit and supports exact request-bound receipt caching. A new compact contract must be implemented and verified before claiming native model completion. Do not silently fall back to the historical Cartesian expansion. Documentation changes, reversible packing and coverage audits alone are not model inspection.

## 1. Freeze scientific scope before expanding tasks

Record the study, comparison direction, cell types, requested contrasts, sensitivity definitions, patient availability and relationship families. Keep the user-requested contrasts even when evidence is weak, nonsignificant, missing or descriptive with one patient. Do not substitute a different scientific pipeline or silently reduce scope to a convenient subset.

Separate three inventories:

1. Immutable source observations, including file/sheet/row and original values.
2. Unique evidence cards and declared scientific questions with source links.
3. Model requests, question heads and responses, including background, unresolved and failed judgments.

An observation can be represented once in a card and referenced by multiple questions. Removing a duplicate representation does not remove a scientific observation. Changing the questions creates a new inspection contract; it does not preserve the meanings of old model answers automatically.

## 2. Choose a meaningful shared evidence card

For cross-cell DEG discovery, the preferred unit is **study × gene**, containing all requested cell types and contrasts for that gene. Keep distinct studies, species, gene identifiers, comparison directions and patient contexts distinguishable. Missing identity must remain unresolved; do not merge unknown identifiers into a fictitious common gene or study.

Keep primary and sensitivity cell definitions together, with their roles marked. A filtered subset of the same cells is not an independent cohort. Preserve duplicate source records and map their identities even when their identical content can share storage.

For meta-analysis, use **clinical question → compatible analysis set**, with selected effect IDs, measure/estimand/stratum compatibility, overlap rules and unresolved dependence. Do not apply gene grouping to clinical ledgers. Publication count, independent evidence, synthesis eligibility and model-inspection completion remain separate.

## 3. Compute facts once; ask only applicable scientific questions

Calculate deterministic quantities once from complete inputs: directions, available patient counts, within-patient signs, missingness, numerical integrity checks and sensitivity differences. Preserve their calculation version and contributing row IDs. A deterministic check is not an Laya/Jev scientific judgment.

For DEG cards, normally declare:

- One integrated review for every gene card, including single-cell-only and unresolved cards.
- A question for each requested cell comparison × contrast supported by source observations. Its scope explicitly includes available primary and sensitivity evidence. Missing primary evidence is marked rather than imputed.
- Sourced, versioned pathway or cross-gene relationship questions when these are part of the user's scope.

Do not multiply every source row and pair by eight generic operators. Do not use the integrated answer, FDR, effect size or top-K ranking to decide whether a declared comparison or relationship receives inspection. Preserve null and opposing patterns. Record missing requested cell/contrast combinations as gaps with reasons.

Same-gene evidence alone does not cover heterologous immune signalling or metabolic pathways. For those scopes, enumerate a separate versioned relationship registry with source, direction, identifiers and evidence links; inspect every eligible declared edge without a first-stage score gate. Missing annotation is unresolved. Do not claim exhaustive pathway coverage from same-gene cards alone.

## 4. Compress reversibly and keep each request self-contained

Store repeated schemas, file context and constants once per card. Use exact tables or dictionaries with an explicit decoder; keep missing, null, empty string and zero distinct. Retain original text, numerical precision, normalized values and conflicting reviews. Before inference, round-trip every observation and compare exact values, source IDs and link multiplicities.

Each model request must contain the evidence and definitions needed for its questions. External row IDs without their actual evidence are insufficient. Shared encodings must be reconstructable within that request. Never replace full evidence by a lossy summary and describe it as full inspection.

Count actual tokens for evidence, questions and options with the deployed tokenizer. If a card is too long, split along declared scientific boundaries, preserve all row/question assignments and add a justified integration step. Page completion is not a joint full-context judgment. If integration cannot fit or has not been implemented, keep the global question incomplete. Never truncate or silently drop rows/questions.

## 5. Reuse only identical judgments

A reusable judgment must bind to the full evidence, question and choices, scientific contract, serializer/calculation versions, provider, model revision, tokenizer, inference settings and request/transport configuration. A matching gene name, candidate title or raw row ID is insufficient.

Maintain dependency links: changed source → affected card → question → relationship/integration → candidate. Recompute affected dependents; reuse successful independent judgments only when the complete binding matches. Do not relabel an old operator answer as an answer to a new integrated question. If the execution scheme couples batch shape or peers to numerical results, include that context in cache identity; unchanged peers may then also require reruns.

Resume with checkpoints and preserve raw receipts. Retry failed items after resolving the cause; leave permanent failures incomplete and stop on repeated systemic failure instead of processing the whole queue as failures.

## 6. Batch and estimate from measured work

Where the backend supports it, batch cards with compatible question definitions and token budgets. Preserve request order, card IDs, question IDs and per-item success; verify returned count, model identity, choices and token usage. Never pad cards with irrelevant questions solely to share a batch. Fewer HTTP requests do not by themselves demonstrate less GPU computation.

Before a long run, validate single versus batch behavior on a declared diagnostic sample spanning short/long cards, missingness, opposing directions and descriptive evidence. This sample is for transport/quality and timing checks; it does not replace the exhaustive inventory. Report label agreement and numerical differences without claiming scientific equivalence.

Estimate total time using measured costs weighted by the full inventory's lengths and question counts. Include new versus cached work, retries, preparation and exports; report uncertainty. Present source rows, logical cards, choice questions and HTTP requests separately. Question-count reduction is not a measured speedup. Report pathway/relationship work separately from the core card pass.

## 7. Acceptance and outputs

Before launching, save a design receipt with input/profile/code hashes, row/card/question inventories, relation-registry versions, mappings, round-trip results, unresolved gaps, token checks, reuse policy and measured cost estimate. For a changed contract, map the previous scope to the new cards/questions and explain any change in semantics. Mapping an old pair is not equivalent to reproducing every old answer.

Completion requires all source observations accounted for, every declared question covered by a valid native receipt (or matching verified cache), all required integrations complete, and zero unexplained missing or failed work. Keep planned coverage, native model coverage and scientific validity separate.

Deliver `candidates.csv` as the primary output, plus candidate–source links, all inspection outcomes (including background), unresolved review queue, immutable inputs/profile/code, raw receipts and verification. Repeated inspections of the same question must not inflate candidate counts. Distinguish posthoc hypotheses from protocol questions and observations from proposed mechanisms. Patient-common patterns require identifiable paired patient evidence; DEG overlap does not prove cell communication, causality or metabolic flux.
