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
    from .ingest import _xlsx, LISTS, BOOLEAN, NUMERIC, adjustment_flag
    sources = list(cfg.get("ledger_inputs", []))
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) - {"entity", "path", "id_column", "columns", "confirmed", "source_reference", "sheet", "transforms"}:
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
        transforms = spec.get('transforms', {})
        if transforms and transforms != {'ci_level': 'percent_to_fraction'}:
            raise ValueError('Ledger transforms support only declared CI percent_to_fraction')
        entries = cfg.setdefault("ledger", {}).setdefault(spec.get("entity"), [])
        for offset, raw in enumerate(rows, 2):
            if None in raw:
                raise ValueError("Malformed ledger row")
            fields = {}
            for field, column in spec["columns"].items():
                value = raw.get(column)
                if field in LISTS:
                    value = [s.strip() for s in str(value or "").split(";") if s.strip()]
                elif field == "effect_adjusted":
                    value = adjustment_flag(value)
                elif field in BOOLEAN:
                    value = boolean(value)
                elif field in NUMERIC:
                    value = number(value)
                    if field == 'ci_level' and transforms.get(field) == 'percent_to_fraction' and value is not None:
                        if not 0 < value <= 100: raise ValueError('Invalid ledger CI percentage')
                        value /= 100
                else:
                    value = str(value).strip() if value not in (None, "") else None
                fields[field] = value
            entries.append({"id": str(raw.get(spec["id_column"], "")).strip(), "fields": fields,
                            "confirmed": spec["confirmed"],
                            "source_reference": f"{spec['source_reference']} [{source.name}, sheet={sheet}, row={offset}]"})
        sources.append({"path": str(source), "sha256": file_hash(source), "rows": len(rows), "sheet": sheet})
    cfg["ledger_inputs"] = sources


def linkage_audit(records, profile):
    """Account for every input and ledger ID. A file being present is not a successful join."""
    from .clinical import IDENTITIES
    cfg = profile.get('clinical', {})
    index = {entity: {x['id']: x for x in entries} for entity, entries in cfg.get('ledger', {}).items()}
    rows = []
    linked = {entity: set() for entity in index}
    for r in records:
        for entity, entries in index.items():
            identifier = r['fields'].get(IDENTITIES[entity])
            hits = [x for x in r['clinical']['links'] if x['entity'] == entity]
            for hit in hits: linked[entity].add(hit['id'])
            rows.append({'record_id': r['id'], 'source_effect_id': r['fields'].get('source_effect_id'),
                         'entity': entity, 'lookup_id': identifier,
                         'status': 'linked_confirmed' if any(x['confirmed'] for x in hits) else 'linked_unconfirmed' if hits else 'missing_id' if not identifier else 'unmatched',
                         'conflicts': r['clinical']['conflicts'], 'source_references': [x['source_reference'] for x in hits]})
    extras = [{'entity': entity, 'id': identifier, 'status': 'not_referenced_by_input',
               'source_reference': entry['source_reference']}
              for entity, entries in index.items() for identifier, entry in entries.items() if identifier not in linked[entity]]
    requirements = cfg.get('ledger_requirements', {})
    if not isinstance(requirements, dict) or set(requirements) - set(IDENTITIES):
        raise ValueError('ledger_requirements uses explicit entity names')
    for entity, requirement in requirements.items():
        if requirement != 'all_input_rows': raise ValueError('Supported ledger requirement: all_input_rows')
        covered = {x['record_id'] for x in rows if x['entity'] == entity and x['status'] == 'linked_confirmed' and not x['conflicts']}
        if len(covered) != len(records):
            raise ValueError(f'Required {entity} ledger linkage incomplete/conflicted: {len(covered)}/{len(records)}')
    return {'rows': rows, 'unused_ledger_entries': extras,
            'coverage': {entity: {'input_rows': len(records), 'confirmed_links': sum(x['entity']==entity and x['status']=='linked_confirmed' for x in rows),
                                 'unmatched_rows': sum(x['entity']==entity and x['status'] in {'missing_id','unmatched'} for x in rows),
                                 'ledger_rows': len(entries), 'unused_entries': len(entries)-len(linked[entity])} for entity, entries in index.items()}}
