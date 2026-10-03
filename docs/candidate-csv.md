# Candidate CSV

**English** | [한국어](candidate-csv.ko.md)

`candidates.csv` is the default user deliverable. `run` writes it automatically and returns its absolute path in `candidate_csv`. A verified `report --out PATH` regenerates exports without calling a model. The entire candidate set is retained, including additional-confirmation items.

| Columns | Meaning |
|---|---|
| `rank`, `id` | Diversity ordering and stable candidate ID; rank is not scientific merit. |
| `route`, `operator`, `focus`, `question` | Hypothesis/follow-up route, inspection perspective, focus and candidate question. |
| `scope_text`, `scope` | Human-readable scope and its structured JSON representation. |
| `record_ids`, `unit_id`, `job_id` | Links to the source records, evidence unit and model inspection. Source IDs are semicolon-separated. |
| `observations`, `limits`, `required_checks` | JSON cells containing observed facts, evidence limitations and unresolved source checks. An empty check list does not mean scientific review is complete. |
| `falsification` | Falsification/review note. The current engine leaves concrete falsification design pending rather than inventing it. |
| `model`, `model_choice`, `model_selection_probability` | Native model identity and categorical judgment. Selection probability is not hypothesis truth or novelty probability. |
| `paper_count`, `unique_study_count`, `paper_count_basis`, `missing_paper_identity_rows` | Cited paper/study counts and whether study IDs were used as paper proxies. Unidentified rows receive no count bonus. |
| `incentive_evidence_count`, `paper_count_bonus`, `ranking_score`, `ranking_paper_count_weight` | Dependency/state-adjusted count, count bonus, combined priority score and configured weight. Score is not a probability. |
| `status` | Candidate's downstream review status. |
| `inspection_status`, `verification_status`, `inspection_coverage` | Whether inspection completed, whether records verified, and inspected fraction from 0 to 1. Incomplete results remain provisional. |

The file uses UTF-8 with BOM, standard CSV quoting, and English field names. Current generated question text is Korean. JSON preserves nested observations and source checks without dropping them into a short prose summary. `candidates.jsonl` and Markdown reports remain supporting files.

With no selected candidates, a header-only CSV is generated. Read `candidate-summary.json` and verification status to distinguish a valid empty result from incomplete inspection. Keep files containing source evidence private unless publication is explicitly authorized.

## Meta-analysis paper count incentive

By default, within each route/operator bucket:

`ranking_score = model_selection_probability + 0.25 * log2(1 + incentive_evidence_count)`

More cited, eligible papers raise priority with diminishing increments. The eligible counts 1, 2, 4 and 8 yield bonuses of approximately 0.250, 0.396, 0.580 and 0.792. The score can exceed 1 and does not establish significance, certainty, novelty or a need to pool the evidence. Round-robin diversity between route/operator buckets remains; the global rank is not a single descending score list.

Counts use only records cited by the candidate, not every paper in the project. Map `publication_id` to a stable paper identifier such as DOI or PMID when available. When it is missing, `study_id` is an explicitly reported proxy; consistent identifiers are required. Multiple rows from one paper, multiple papers from one study, and declared shared cohorts form dependency groups. A group contributes at most one bonus unit, and only when it contains an identified row that is neither source-blocked nor held. Blocked/held rows remain inspected and reported. No declared cohort link is not proof of independence. These counts do not replace source or risk-of-bias review.

Override the default weight in a new project profile (0–1; 0 disables the incentive):

```yaml
ranking:
  paper_count_weight: 0.25
```

The incentive applies to meta-analysis only, after every planned model inspection. It never excludes low-count candidates or reduces inspection coverage. DEG ordering receives no paper-count bonus. Existing frozen runs and profiles retain their original contracts; create a new plan with updated code rather than editing a frozen run to resume it.
