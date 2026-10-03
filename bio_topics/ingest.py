"""CSV/TSV/XLSX adapters. Source values are retained, never imputed by a model."""
import csv
import json
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .util import boolean, digest, number
from .ranking import ranking_policy
from .clinical import prepare, validate_config, enabled
from .ledger import expand_ledger_files

NUMERIC = {"log2fc", "fdr", "p_value", "value", "ci_lower", "ci_upper", "ci_level", "se", "n", "df"}
BOOLEAN = {"human_checked", "synthesis_approved", "source_blocked", "primary_candidate"}
LISTS = {"cohort_ids", "adjustment_variables"}


def read_profile(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() == ".json":
        profile = json.loads(text)
    else:
        try:
            import yaml
        except ImportError:
            raise ValueError("YAML에는 PyYAML이 필요합니다. 같은 설정을 JSON으로 제공할 수도 있습니다.") from None
        profile = yaml.safe_load(text)
    if not isinstance(profile, dict):
        raise ValueError("프로파일은 객체여야 합니다.")
    if profile.get("schema_version") != 1 or profile.get("domain") not in ("deg", "meta"):
        raise ValueError("schema_version: 1 및 domain: deg 또는 meta가 필요합니다.")
    if not isinstance(profile.get("columns"), dict):
        raise ValueError("columns 열 매핑이 필요합니다.")
    expand_ledger_files(profile, path)
    validate_config(profile)
    ranking_policy(profile)
    transforms = profile.get("transforms", {})
    if not isinstance(transforms, dict) or any(k != "ci_level" or v != "percent_to_fraction" for k, v in transforms.items()):
        raise ValueError("지원되는 변환은 transforms.ci_level: percent_to_fraction입니다.")
    if not isinstance(profile.get("question"), str) or not profile["question"].strip():
        raise ValueError("프로젝트 연구 질문(question)이 필요합니다.")
    contract = profile.get("inspection", {})
    if contract.get("pairs") not in ("all", "within_groups", "within_questions", "none"):
        raise ValueError("inspection.pairs를 all / within_groups / within_questions / none 중 하나로 선언하세요.")
    if contract["pairs"] == "within_groups" and not contract.get("pair_group_by"):
        raise ValueError("within_groups에는 pair_group_by가 필요합니다.")
    if contract["pairs"] == "within_questions" and not (profile["domain"] == "meta" and profile.get("clinical", {}).get("enabled", True)):
        raise ValueError("within_questions requires clinical meta mode")
    if not contract.get("cell_fields"):
        raise ValueError("inspection.cell_fields를 선언하세요.")
    synthesis = profile.get("synthesis", {})
    if synthesis.get("enabled"):
        if profile["domain"] != "meta":
            raise ValueError("효과량 합성은 meta 도메인에서만 지원합니다.")
        if synthesis.get("policy") != "one_per_dependency_component":
            raise ValueError("v0.1은 one_per_dependency_component 정책만 지원합니다.")
        methods = synthesis.get("methods", [])
        if not methods or any(m not in ("fixed_iv", "random_dl") for m in methods):
            raise ValueError("합성 방법은 fixed_iv / random_dl을 명시하세요.")
        if not synthesis.get("required_fields"):
            raise ValueError("합성에 필요한 메타데이터(required_fields)를 선언하세요.")
    relations = profile.get("knowledge_relations", [])
    if not isinstance(relations, list) or any(not isinstance(r, dict) or not all(r.get(k) for k in ("source", "target", "type", "source_reference")) for r in relations):
        raise ValueError("knowledge_relations는 source/target/type/source_reference가 있는 관계 목록이어야 합니다.")
    return profile


def _xlsx(path, sheet):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        # Reject oversize/hostile files explicitly; do not ingest a prefix and call it complete.
        if sum(i.file_size for i in archive.infolist()) > 256 * 1024 * 1024:
            raise ValueError("XLSX 압축 해제 크기가 256 MiB를 넘습니다. 전체 CSV로 변환하세요.")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.find("s:sheets", ns)
        if sheets is None or len(sheets) == 0:
            raise ValueError("XLSX에 시트가 없습니다.")
        if len(sheets) > 1 and sheet is None:
            raise ValueError("여러 시트가 있습니다. profile.sheet로 사용할 시트를 선언하세요.")
        selected = next((s for s in sheets if sheet is None or s.attrib["name"] == sheet), None)
        if selected is None:
            raise ValueError(f"시트를 찾지 못했습니다: {sheet}")
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rid = selected.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == rid)
        member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for si in ET.fromstring(archive.read("xl/sharedStrings.xml")):
                shared.append("".join(t.text or "" for t in si.iter("{" + ns["s"] + "}t")))
        rows = []
        for row in ET.fromstring(archive.read(member)).findall(".//s:sheetData/s:row", ns):
            values = {}
            for cell in row:
                letters = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
                if letters is None:
                    raise ValueError("셀 좌표가 없는 XLSX는 지원하지 않습니다.")
                col = 0
                for c in letters[0]:
                    col = col * 26 + ord(c) - 64
                node = cell.find("s:v", ns)
                if cell.find("s:f", ns) is not None:
                    raise ValueError("수식 셀이 있습니다. 값으로 저장한 XLSX 또는 CSV를 제공하세요.")
                if cell.attrib.get("t") == "e":
                    raise ValueError("Excel 오류 셀이 있습니다.")
                value = node.text if node is not None else ""
                if cell.attrib.get("t") == "s":
                    value = shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//s:t", ns))
                values[col - 1] = value
            if values and any(v != "" for v in values.values()):
                rows.append([values.get(i, "") for i in range(max(values) + 1)])
        if not rows:
            raise ValueError("시트에 데이터가 없습니다.")
        headers = rows[0]
        return headers, [dict(zip(headers, r + [""] * (len(headers) - len(r)))) for r in rows[1:]], selected.attrib["name"]


def read_table(path, profile):
    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        headers, raw_rows, sheet = _xlsx(path, profile.get("sheet"))
    elif suffix in (".csv", ".tsv"):
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter="\t" if suffix == ".tsv" else ",")
            headers = reader.fieldnames or []
            raw_rows = list(reader)
        sheet = None
    else:
        raise ValueError("CSV, TSV, XLSX를 지원합니다. 구형 .xls는 변환하세요.")
    if not headers or len(set(headers)) != len(headers) or any(not h for h in headers):
        raise ValueError("열 이름이 비었거나 중복입니다.")
    missing_columns = sorted(set(profile["columns"].values()) - set(headers))
    if missing_columns:
        raise ValueError(f"매핑한 원본 열이 없습니다: {missing_columns}")
    if not raw_rows:
        raise ValueError("입력 행이 없습니다. 빈 데이터로 전수 완료를 만들지 않습니다.")
    required = {"entity_id", "comparison"} if profile["domain"] == "deg" else ({"measure", "value"} if enabled(profile) else {"study_id", "measure", "value"})
    if required - profile["columns"].keys():
        raise ValueError(f"필수 열 매핑 누락: {sorted(required - profile['columns'].keys())}")
    records = []
    for offset, raw in enumerate(raw_rows, 2):
        if None in raw:
            raise ValueError(f"원본 {offset}행에 헤더보다 많은 값이 있습니다.")
        fields, parse_issues = {}, []
        for field, column in profile["columns"].items():
            value = raw.get(column)
            try:
                if field in NUMERIC:
                    value = number(value)
                    if value is not None and profile.get("transforms", {}).get(field) == "percent_to_fraction":
                        if not 0 < value <= 100:
                            raise ValueError("CI 백분율이 0~100 범위를 벗어남")
                        value /= 100
                elif field in BOOLEAN:
                    value = boolean(value)
                elif field in LISTS:
                    value = [v.strip() for v in str(value or "").split(";") if v.strip()]
                else:
                    value = str(value).strip() if value not in (None, "") else None
            except ValueError as exc:
                parse_issues.append({"field": field, "issue": str(exc)})
                value = None
            fields[field] = value
        for field, value in profile.get("declarations", {}).items():
            if field in fields and fields[field] is not None and fields[field] != value:
                raise ValueError(f"{offset}행 {field}: 원본과 프로파일 선언이 충돌합니다.")
            fields[field] = value
        rid = "R" + digest([offset, sheet, raw])[:20]
        records.append({"id": rid, "domain": profile["domain"], "source_row": offset,
                        "sheet": sheet, "fields": fields, "raw": raw, "parse_issues": parse_issues})
    records = prepare(records, profile)
    return records, {"headers": headers, "mapped_columns": profile["columns"],
                     "unmapped_columns": sorted(set(headers) - set(profile["columns"].values())),
                     "source_sheet": sheet, "rows": len(records),
                     "missing_values": {f: sum(r["fields"].get(f) is None for r in records)
                                        for f in profile["columns"]}}
