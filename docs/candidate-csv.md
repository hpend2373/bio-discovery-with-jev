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
| `status` | Candidate's downstream review status. |
| `inspection_status`, `verification_status`, `inspection_coverage` | Whether inspection completed, whether records verified, and inspected fraction from 0 to 1. Incomplete results remain provisional. |

The file uses UTF-8 with BOM, standard CSV quoting, and English field names. Current generated question text is Korean. JSON preserves nested observations and source checks without dropping them into a short prose summary. `candidates.jsonl` and Markdown reports remain supporting files.

With no selected candidates, a header-only CSV is generated. Read `candidate-summary.json` and verification status to distinguish a valid empty result from incomplete inspection. Keep files containing source evidence private unless publication is explicitly authorized.
