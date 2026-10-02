import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    os.replace(tmp, path)


def number(value):
    if value in (None, "", "unknown", "NA", "N/A", "NaN"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"수치로 읽을 수 없는 값: {value!r}") from None
    if not math.isfinite(result):
        raise ValueError(f"유한하지 않은 수치: {value!r}")
    return result


def boolean(value):
    if isinstance(value, bool):
        return value
    if str(value).strip().lower() in ("true", "1", "yes", "승인"):
        return True
    if str(value).strip().lower() in ("false", "0", "no", "미승인"):
        return False
    if value in (None, "", "unknown"):
        return None
    raise ValueError(f"참/거짓으로 읽을 수 없는 값: {value!r}")


def source_hash():
    root = Path(__file__).parent
    return digest({p.name: file_hash(p) for p in sorted(root.glob("*.py"))})
