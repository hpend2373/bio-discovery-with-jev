import json
import os
import shutil
import time
from collections import Counter
from pathlib import Path

from .clinical import audit, enabled
from .backend import HTTPBackend, slice_receipt, validate_receipt, validate_response
from .ingest import read_profile, read_table
from .plan import batch_questions, enumerate_units, operators, preflight, questions
from .partitioning import make_pages, execution_units, FORMAT
from .report import export_report
from .store import Cache, connect, counts, get_meta, initialize, set_meta
from .util import canonical, digest, file_hash, now, source_hash, write_json


def create_plan(input_path, profile_path, out, context_checker=None):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("출력 폴더가 이미 있습니다. 새 실행 폴더를 쓰거나 run으로 재개하세요.")
    profile = read_profile(profile_path)
    records, mapping = read_table(input_path, profile)
    flight = preflight(records, profile)
    tmp = out.with_name(out.name + ".planning")
    if tmp.exists():
        raise ValueError("이전 계획 임시 폴더가 있습니다. 확인 후 다른 출력 이름을 사용하세요.")
    tmp.mkdir(parents=True)
    planning_backend = None
    partition_index = None
    try:
        if profile['inspection'].get('partition_long_evidence'):
            config = profile.get('backend', {})
            identity = None
            if context_checker is None:
                if config.get('kind', 'laya') == 'laya':
                    planning_backend = HTTPBackend(config)
                    identity = planning_backend.identity
                    context_checker = lambda state: planning_backend.guard.check(state, batch_questions(profile), planning_backend.max_len, planning_backend.head_max_len)
                else:
                    limit = config.get('max_body_bytes', 262144)
                    def context_checker(state):
                        payload = {'state': state, 'model': config.get('model'), 'questions': batch_questions(profile)}
                        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())
                        if size > limit: raise ValueError('request body exceeds byte budget')
                        return {'ok': True, 'body_bytes': size}
            partition_index = {'format': FORMAT, 'provider': identity, 'parents': {}}
        ledger_files = {}
        for i, source in enumerate(profile.get("clinical", {}).get("ledger_inputs", [])):
            original = Path(source["path"])
            target = "ledger_inputs/" + str(i) + original.suffix.lower()
            (tmp / "ledger_inputs").mkdir(exist_ok=True)
            shutil.copyfile(original, tmp / target)
            if file_hash(tmp / target) != source["sha256"]:
                raise ValueError("Ledger file changed while planning")
            ledger_files[target] = source["sha256"]
        write_json(tmp / "profile.json", profile)
        write_json(tmp / "records.json", records)
        if enabled(profile):
            write_json(tmp / "clinical-audit.json", audit(records, profile))
            from .ledger import linkage_audit
            from .clinical_report import write_csv
            linkage = linkage_audit(records, profile)
            write_json(tmp / 'ledger-linkage.json', linkage)
            write_csv(tmp / 'ledger-linkage.csv', linkage['rows'], ['record_id', 'source_effect_id', 'entity', 'lookup_id', 'status', 'conflicts', 'source_references'])
            write_csv(tmp / 'unused-ledger-entries.csv', linkage['unused_ledger_entries'], ['entity', 'id', 'status', 'source_reference'])
        frozen_input = "input" + Path(input_path).suffix.lower()
        shutil.copyfile(input_path, tmp / frozen_input)
        write_json(tmp / "mapping.json", mapping)
        db = connect(tmp / "inspection.sqlite3")
        initialize(db)
        kind_counts = Counter()
        unit_chain = ""
        job_chain = ""
        unit_count = job_count = 0
        names = operators(profile)
        logical_counts = Counter()
        logical_seen = set()
        def planned_units():
            for parent in enumerate_units(records, profile):
                if parent['id'] in logical_seen: continue
                logical_seen.add(parent['id']); logical_counts[parent['kind']] += 1
                if partition_index is None:
                    yield parent
                else:
                    pages, spec = make_pages(parent, context_checker)
                    partition_index['parents'][parent['id']] = spec
                    yield from pages
        for u in planned_units():
            # Identical LOO scenarios from distinct full universes can be deduplicated only
            # when the complete unit, including full estimate and excluded record, is identical.
            body = canonical(u)
            if db.execute("SELECT 1 FROM units WHERE id=?", (u["id"],)).fetchone():
                continue
            unit_count += 1
            h = digest(u)
            db.execute("INSERT INTO units(seq,id,kind,body,hash) VALUES (?,?,?,?,?)", (unit_count, u["id"], u["kind"], body, h))
            unit_chain = digest([unit_chain, u["id"], h])
            kind_counts[u["kind"]] += 1
            for operator in names:
                q = questions(operator)
                jid = "J" + digest([u["id"], operator, q])[:24]
                job_count += 1
                db.execute("INSERT INTO jobs(seq,id,unit_id,operator,questions) VALUES (?,?,?,?,?)", (job_count, jid, u["id"], operator, canonical(q)))
                job_chain = digest([job_chain, jid, digest(q)])
            if unit_count % 250 == 0:
                db.commit()
                print(canonical({"stage": "planning", "units": unit_count, "jobs": job_count}), flush=True)
        db.commit()
        if logical_counts["row"] != len(records) or logical_counts["pair"] != flight["pairs"] or logical_counts["cell"] != flight["cells"] or logical_counts["analysis_set"] != flight.get("analysis_sets", 0):
            raise ValueError("검사 목록의 행·셀·관계 수가 독립 계산과 불일치")
        contract = {"schema_version": 1, "input_file": frozen_input, "input_hash": file_hash(tmp / frozen_input),
                    "ledger_files": ledger_files, "profile_hash": digest(profile), "records_hash": digest(records), "code_hash": source_hash(),
                    "unit_count": unit_count, "job_count": job_count, "units_by_kind": dict(kind_counts),
                    "unit_chain": unit_chain, "job_chain": job_chain, "operators": names, "preflight": flight}
        if partition_index is not None:
            write_json(tmp / 'partition-plan.json', partition_index)
            contract.update(partition_hash=digest(partition_index), logical_units_by_kind=dict(logical_counts),
                            logical_unit_count=sum(logical_counts.values()), context_preflight='all_pages_fit',
                            context_semantics='local_page_judgments_with_complete_declared_pair_fields')
        set_meta(db, "contract", contract)
        db.close()
        shutil.copytree(Path(__file__).parent, tmp / "source" / "bio_topics", ignore=shutil.ignore_patterns("__pycache__"))
        write_json(tmp / "manifest.json", {"status": "planned", "created": now(), "contract": contract,
                                         "downstream_review": "pending"})
        os.replace(tmp, out)
        return {"run": str(out), **contract}
    except BaseException:
        # Preserve failed planning artifacts for inspection; never label them as a run.
        write_json(tmp / "planning-failure.json", {"status": "planning_failed", "time": now()})
        raise
    finally:
        if planning_backend: planning_backend.close()


def verify(out):
    out = Path(out)
    db = connect(out / "inspection.sqlite3")
    contract = get_meta(db, "contract")
    errors = []
    if source_hash() != contract["code_hash"]:
        errors.append("code_fingerprint_changed: use this run's source snapshot")
    profile = json.loads((out / "profile.json").read_text())
    records = json.loads((out / "records.json").read_text())
    if digest(profile) != contract["profile_hash"] or digest(records) != contract["records_hash"]:
        errors.append("frozen_profile_or_records_changed")
    if file_hash(out / contract["input_file"]) != contract["input_hash"]:
        errors.append("frozen_input_changed")
    for name, expected in contract.get("ledger_files", {}).items():
        if not (out / name).exists() or file_hash(out / name) != expected:
            errors.append("frozen_ledger_changed:" + name)
    reparsed, _ = read_table(out / contract["input_file"], profile)
    if digest(reparsed) != digest(records):
        errors.append("normalized_records_do_not_match_source")
    index = json.loads((out / 'partition-plan.json').read_text()) if contract.get('partition_hash') else None
    if index is not None and digest(index) != contract['partition_hash']:
        errors.append('partition_plan_changed')
    unit_chain = job_chain = ""
    all_q = batch_questions(profile)
    seen = set()
    n_units = n_jobs = 0
    kind_counts = Counter()
    for u in execution_units(records, profile, index):
        if u["id"] in seen:
            continue
        seen.add(u["id"])
        n_units += 1
        kind_counts[u["kind"]] += 1
        h = digest(u)
        unit_chain = digest([unit_chain, u["id"], h])
        saved = db.execute("SELECT * FROM units WHERE id=?", (u["id"],)).fetchone()
        if saved is None or saved["hash"] != h or digest(json.loads(saved["body"])) != h:
            errors.append("missing_or_modified_unit:" + u["id"])
        for op in operators(profile):
            q = questions(op)
            jid = "J" + digest([u["id"], op, q])[:24]
            n_jobs += 1
            job_chain = digest([job_chain, jid, digest(q)])
            job = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if job is None or job["unit_id"] != u["id"] or job["operator"] != op or json.loads(job["questions"]) != q:
                errors.append("missing_or_modified_job:" + jid)
                continue
            if job["status"] in ("evaluated", "cached"):
                try:
                    receipt = json.loads(job["receipt"])
                    if digest(receipt) != job["receipt_hash"]:
                        raise ValueError("receipt_hash")
                    identity = get_meta(db, "provider")
                    if receipt["provider_identity"] != identity or digest([identity, u["state"], q, all_q]) != job["cache_key"]:
                        raise ValueError("provider_or_cache_binding")
                    validate_receipt(receipt, u["state"], q, identity, all_q, op)
                except (ValueError, KeyError, TypeError):
                    errors.append("invalid_receipt:" + jid)
    flight = preflight(records, profile)
    logical_counts = Counter(u['kind'] for u in enumerate_units(records, profile)) if index is not None else kind_counts
    if logical_counts["row"] != len(records) or logical_counts["pair"] != flight["pairs"] or logical_counts["cell"] != flight["cells"] or logical_counts["analysis_set"] != flight.get("analysis_sets", 0):
        errors.append("independent_coverage_counts_mismatch")
    saved_units = db.execute("SELECT count(*) FROM units").fetchone()[0]
    saved_jobs = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
    if (n_units, n_jobs, saved_units, saved_jobs) != (contract["unit_count"], contract["job_count"], n_units, n_jobs):
        errors.append("manifest_counts_mismatch")
    if unit_chain != contract["unit_chain"] or job_chain != contract["job_chain"]:
        errors.append("inspection_contract_changed")
    stats = counts(db)
    if stats["successful"] != contract["job_count"] or stats["failed"] or stats["pending"]:
        errors.append("unresolved_model_inspections")
    logical_status = None
    if index is not None:
        from .clinical_report import write_csv
        parents = {}
        for u in db.execute('SELECT id,body FROM units ORDER BY seq'):
            body = json.loads(u['body']); pid = body.get('parent_unit_id', body['id'])
            item = parents.setdefault(pid, {'parent_unit_id': pid, 'kind': body['kind'], 'pages': 0, 'successful_pages': 0,
                                           'joint_full_context': 'parent_unit_id' not in body})
            statuses = [j[0] for j in db.execute('SELECT status FROM jobs WHERE unit_id=?', (u['id'],))]
            item['pages'] += 1
            item['successful_pages'] += bool(statuses) and all(v in {'evaluated','cached'} for v in statuses)
        for item in parents.values(): item['completed'] = item['pages'] == item['successful_pages']
        write_csv(out / 'partition-coverage.csv', parents.values(), ['parent_unit_id','kind','pages','successful_pages','completed','joint_full_context'])
        logical_status = {'planned': len(parents), 'completed': sum(x['completed'] for x in parents.values()),
                          'partitioned_parents': sum(not x['joint_full_context'] for x in parents.values()),
                          'meaning': 'All pages inspected; partitioned parents do not have a single joint full-context judgment.'}
    simulated = get_meta(db, "simulated") is True
    if simulated:
        errors.append("simulated_backend_not_scientific_coverage")
    db.close()
    result = {"status": "verified" if not errors else "incomplete_or_invalid", "checked": now(),
              "counts": stats, "errors": errors, "candidate_truth_validated": False,
              "downstream_review": "pending"}
    if logical_status is not None: result["logical_units"] = logical_status
    write_json(out / "verification.json", result)
    return result


def run(out, allow_external=False, retry_failed=False, backend=None):
    out = Path(out)
    db = connect(out / "inspection.sqlite3")
    contract = get_meta(db, "contract")
    profile = json.loads((out / "profile.json").read_text())
    if source_hash() != contract["code_hash"]:
        raise ValueError("코드가 바뀌었습니다. 실행 폴더의 source 스냅샷으로 재개하거나 새 계획을 만드세요.")
    if digest(profile) != contract["profile_hash"] or digest(json.loads((out / "records.json").read_text())) != contract["records_hash"] or file_hash(out / contract["input_file"]) != contract["input_hash"]:
        raise ValueError("고정된 입력 또는 프로파일이 변경되었습니다.")
    made_backend = backend is None
    backend = backend or HTTPBackend(profile.get("backend", {}), allow_external)
    cache = None
    manifest = json.loads((out / "manifest.json").read_text())
    try:
        if contract.get('partition_hash'):
            index = json.loads((out / 'partition-plan.json').read_text())
            if digest(index) != contract['partition_hash']: raise ValueError('Partition plan changed')
            if index['provider'] is not None and index['provider'] != backend.identity:
                raise ValueError('Preflight backend/tokenizer differs from execution backend')
        old_provider = get_meta(db, "provider")
        if old_provider is not None and old_provider != backend.identity:
            raise ValueError("백엔드·모델·토크나이저가 변경되어 같은 실행으로 재개할 수 없습니다.")
        set_meta(db, "provider", backend.identity)
        set_meta(db, "simulated", bool(getattr(backend, "simulated", False)))
        if retry_failed:
            db.execute("UPDATE jobs SET status='pending',error=NULL WHERE status='failed'")
            db.commit()
        cache = Cache(out.parent / "decision-cache.sqlite3")
        manifest.update(status="running", updated=now(), provider=backend.identity)
        write_json(out / "manifest.json", manifest)
        last_progress = 0
        all_q = batch_questions(profile)
        while True:
            row = db.execute("SELECT j.*,u.body FROM jobs j JOIN units u ON j.unit_id=u.id WHERE j.status='pending' ORDER BY j.seq LIMIT 1").fetchone()
            if row is None:
                break
            u = json.loads(row["body"])
            group = list(db.execute("SELECT * FROM jobs WHERE unit_id=? AND status='pending' ORDER BY seq", (row["unit_id"],)))
            pending = []
            try:
                for job in group:
                    q = json.loads(job["questions"])
                    key = digest([backend.identity, u["state"], q, all_q])
                    receipt = cache.get(key)
                    if receipt is None:
                        pending.append((job, q, key))
                    else:
                        validate_receipt(receipt, u["state"], q, backend.identity, all_q, job["operator"])
                        db.execute("UPDATE jobs SET status='cached',error=NULL,receipt=?,receipt_hash=?,cache_key=?,updated=? WHERE id=?",
                                   (canonical(receipt), digest(receipt), key, now(), job["id"]))
                db.commit()
                if pending:
                    for job, _, _ in pending:
                        db.execute("UPDATE jobs SET attempts=attempts+1,updated=? WHERE id=?", (now(), job["id"]))
                    db.commit()
                    full_receipt = backend.evaluate(u["state"], all_q)
                    validate_response(full_receipt["payload"], all_q)
                    receipts = []
                    for job, q, key in pending:
                        receipt = slice_receipt(full_receipt, job["operator"], u["state"], all_q)
                        validate_receipt(receipt, u["state"], q, backend.identity, all_q, job["operator"])
                        receipts.append((job, key, receipt))
                    for job, key, receipt in receipts:
                        cache.put(key, receipt)
                        db.execute("UPDATE jobs SET status='evaluated',error=NULL,receipt=?,receipt_hash=?,cache_key=?,updated=? WHERE id=?",
                                   (canonical(receipt), digest(receipt), key, now(), job["id"]))
            except (ValueError, RuntimeError, OSError) as exc:
                db.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE unit_id=? AND status='pending'", (str(exc), now(), row["unit_id"]))
            db.commit()
            if time.monotonic() - last_progress > 10:
                stats = counts(db)
                print(canonical({"stage": "inspection", **stats}), flush=True)
                manifest.update(counts=stats, updated=now())
                write_json(out / "manifest.json", manifest)
                last_progress = time.monotonic()
    except KeyboardInterrupt:
        manifest.update(status="interrupted", updated=now(), counts=counts(db))
        write_json(out / "manifest.json", manifest)
        raise
    finally:
        db.close()
        if cache:
            cache.close()
        if made_backend:
            backend.close()
    result = verify(out)
    manifest.update(status="completed" if result["status"] == "verified" else "incomplete",
                    updated=now(), counts=result["counts"], verification=result["status"])
    write_json(out / "manifest.json", manifest)
    candidate_count = export_report(out)
    return {**result, "run": str(out), "candidates": candidate_count,
            "candidate_csv": str((out / "candidates.csv").resolve())}
