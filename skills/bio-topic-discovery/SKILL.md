---
name: bio-topic-discovery
description: Inspect every declared unit of DEG/omics tables, CellChat exports or meta-analysis ledgers with local Laya or explicitly selected Jev to discover evidence-linked biological research questions. Use for data-driven exhaustive candidate discovery, resume and coverage verification; not raw sequencing analysis or clinical advice.
---

# Exhaustive biological research candidate inspection

**English** | [한국어](SKILL.ko.md)

The engine is this repository's `bio_topics` package. Install it with `pip install -e .`. `scripts/run.py` locates the repository engine or an installed package; use `--project PATH` or `BIO_TOPIC_DISCOVERY_ROOT` for another installation. Read [references/workflow.md](references/workflow.md) for new inputs and runs. Respond in the user's language, including English or Korean. Current engine-generated reports use Korean filenames and text.

## Default design for new work

Before planning, redesigning or restarting, read [evidence-first exhaustive inspection](references/efficient-inspection.md). Preserve every source row and declared relationship while sharing study×gene cards (clinical-question×analysis-set evidence for meta-analysis), separating deterministic facts from scientific questions, and eliminating redundant or inapplicable questions. Row/cell/pair × eight operators is a historical contract, not the default design. Use `--legacy-deg` only for an intentionally selected historical contract; never add it silently to bypass this policy.

Report source coverage, actual model coverage and scientific validation separately. When the new card executor, multi-card batching or dependency cache is not implemented, state that limitation and implement/verify it before a production run. Do not silently resume the historical expansion or claim completion or speedup from a design audit.

## Core contract

- Adapters and deterministic facts prepare the evidence. **Every declared inspection unit needs an actual Laya/Jev response for inspection to be complete.** Do not reduce scope with FDR, importance, top-K, time, or count cutoffs.
- Freeze source-to-card links, applicable questions, declared relations and supported synthesis scenarios before execution. Define pair scope according to the user's scientific intent and report its size. Do not silently exclude pairs or redefine the user's exhaustive request.
- Inspect weak, held, and blocked evidence too. Approval for synthesis or conclusions is separate. Do not fill profile unknowns with model guesses.
- Preserve originals and use a new run directory. Resume only with matching input, profile, code, model, and tokenizer. Resolve causes before retrying failed inspections; persistent failures remain incomplete.
- Reuse existing local Laya by default; do not restart servers or load extra model weights without user authorization. Use `--allow-external` only when the user explicitly selects transmitting evidence to Jev. Pass API keys through environment variables and keep them private.
- Truncated evidence, questions, or choices cannot count as successful. Do not turn failures or missing evidence into a finding of no candidates.

## Workflow

1. Inspect columns and study context, then create a project-specific JSON/YAML profile. Do not copy synthetic scientific definitions into real inputs. Make routine mapping decisions; clarify only unresolved scientific choices that change the result, such as estimands, comparison direction, timing, and pair scope.
2. After verifying that the selected executor implements the declared design, run `plan` and inspect `mapping.json` and `manifest.json`. Explain source-row inclusion, declared scope, and synthesis exclusions, then continue authorized work.
3. Run exhaustive evaluation and report progress. Share evidence across applicable questions while retaining individual judgments; distinguish single-card question batching from multi-card batching.
4. Verify `verified`, manifest `completed`, 100% coverage, and zero failed/pending inspections. Synthetic tests or rule substitutions are not evidence of actual model inspection.
5. Deliver **`candidates.csv` as the primary result**, with a clickable absolute file link. Read it together with `candidates.jsonl` and source evidence, check evidence/confirmation fields and inspection status, and present a concise summary. Keep every candidate in the CSV; Markdown/JSONL are supporting materials. Clearly mark incomplete inspections as provisional. If no candidates exist, deliver the header-only CSV and state the inspection status. Do not publish candidate CSVs containing private evidence without explicit authorization.
6. Continue literature and System 2 review within the requested scope. Separate observations from hypotheses, record contrary evidence, falsification conditions, follow-up analyses/experiments, and sources. Do not invent literature, numbers, causal effects, or metabolic flux. Do not automatically mark review or human adoption complete.

Meta-regression, funnel tests, joint diagnostic-accuracy synthesis, complex covariance models are unsupported. The historical executor offers opt-in paging; new designs require actual length checks and explicit integration semantics. Declared coverage does not imply every possible analysis was performed. Jev integration is implemented; live API validation remains separate.

## Current quality limits

Candidate titles are templates derived from categorical decisions; synthesis warnings can affect routing. Inspection counts and choice probabilities are not numbers of novel topics or scientific validity scores. Distinguish native model labels from questions developed by subsequent reviewers. Literature, novelty, and falsifiability review remain separate. Public computing time and result interpretation are in `docs/evaluation/`.

## Clinical questions and analysis sets (v0.3)

Declare upper-question, stratum and sensitivity dimensions in `clinical.partition`; model, lag and follow-up changes do not normally create separate upper questions. Use researcher-grounded project rules, never copied synthetic scientific declarations. Read the engine's `docs/clinical-pipeline.md` and `profiles/meta.clinical.example.yaml`.

Read independent counts from `analysis_sets.csv`, attached to selected effect rows and explicit overlap rules. Documented sampling frames (institutions, periods, eligibility) can support independence at a declared evidence level; unresolved counts stay blank. Inspect all allowed alternatives. Never choose a representative estimate by effect direction, significance or SE. Report publication counts separately; the optional bonus defaults to zero and is capped at one credit per confirmed selected participant identity. Priority is for review, not pooling weights or certainty.

`candidates.csv` contains upper-question families; `inspection_results.csv` retains all jobs; `candidate_effects.csv` connects every same-question effect and role, including opposing, null, background and held evidence. Distinguish protocol, posthoc exploratory and validation questions with source/date provenance. Unregistered discoveries and new result-driven hypotheses remain posthoc exploratory. Model completion does not certify source verification, independent dual review, outcome RoB or synthesis approval; each gate requires its own supplied evidence. Preserve old source snapshots and use a new run for changed code or policy.

## v0.4

Read `docs/long-evidence.md` in the engine. Enable `inspection.partition_long_evidence: true` in new profiles for preflighted, lossless pages. Verify all pages and logical parents; report local-page coverage separately from joint full-context reasoning. Use `link-ledger` with exact effect IDs, preserve all missing/conflicting/unused rows, and never reconstruct a missing source ledger by assumption.

## CellChat

For CellChat results, read [the CellChat workflow](references/cellchat.md). Use `cellchat plan/run/verify`; preserve all supplied edges, direction, complex/cofactor annotations and source IDs. Report provided-row versus stored-tensor coverage. Do not convert communication scores to DEG effects or infer missing edges as zero.
