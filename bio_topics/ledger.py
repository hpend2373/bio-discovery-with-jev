"""Materialize explicitly mapped CSV/XLSX ledgers into the frozen profile."""
import csv
from pathlib import Path

from .util import boolean, file_hash, number


def expand_ledger_files(profile, profile_path):
    cfg = profile.get("clinical", {})
    specs = cfg.pop("ledger_files", []) if isinstance(cfg, dict) else []
    if not isinstance(specs, list):
        raise ValueError("clinical.ledger_files must be a list")
    if not specs:
        return
    from .ingest import _xlsx, LISTS, BOOLEAN, NUMERIC
    sources = []
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) - {"entity", "path", "id_column", "columns", "confirmed", "source_reference", "sheet"}:
            raise ValueError("Invalid ledger file specification")
        if not isinstance(spec.get("path"), str) or not isinstance(spec.get("columns"), dict) or not isinstance(spec.get("confirmed"), bool) or not spec.get("source_reference"):
            raise ValueError("Ledger file requires path, columns, confirmed and source_reference")
        source = (Path(profile_path).resolve().parent / spec["path"]).resolve()
        suffix = source.suffix.lower()
        if suffix == ".xlsx":
            headers, rows, sheet = _xlsx(source, spec.get("sheet"))
        elif suffix in (".csv", ".tsv"):
            with source.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t" if suffix == ".tsv" else ",")
                headers, rows, sheet = reader.fieldnames or [], list(reader), None
        else:
            raise ValueError("Ledger files must be CSV, TSV or XLSX")
        if len(set(headers)) != len(headers) or not headers or any(not h for h in headers):
            raise ValueError("Invalid ledger header")
        if spec.get("id_column") not in headers or set(spec["columns"].values()) - set(headers):
            raise ValueError("Ledger column mapping does not match source")
        entries = cfg.setdefault("ledger", {}).setdefault(spec.get("entity"), [])
        for offset, raw in enumerate(rows, 2):
            if None in raw:
                raise ValueError("Malformed ledger row")
            fields = {}
            for field, column in spec["columns"].items():
                value = raw.get(column)
                if field in LISTS:
                    value = [s.strip() for s in str(value or "").split(";") if s.strip()]
                elif field in BOOLEAN or field == "effect_adjusted":
                    value = boolean(value)
                elif field in NUMERIC:
                    value = number(value)
                else:
                    value = str(value).strip() if value not in (None, "") else None
                fields[field] = value
            entries.append({"id": str(raw.get(spec["id_column"], "")).strip(), "fields": fields,
                            "confirmed": spec["confirmed"],
                            "source_reference": f"{spec['source_reference']} [{source.name}, sheet={sheet}, row={offset}]"})
        sources.append({"path": str(source), "sha256": file_hash(source), "rows": len(rows), "sheet": sheet})
    cfg["ledger_inputs"] = sources
