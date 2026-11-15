"""Scheme catalog: reads EVERY *.json file in data/catalog/ (files starting with _ are ignored).

Unknown information stays None ("not officially verified") - it is never guessed."""
import hashlib
import json
from functools import lru_cache

import db_config
from backend.utils import norm

NOT_STATED = "Not stated - verify on the official portal"


def _list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(v).strip() for v in value if str(v).strip()]


def _num(value):
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def normalize_record(raw: dict) -> dict:
    """Accept old (starter) and new records; return one standard shape."""
    category = raw.get("category")
    extra = _list(raw.get("additional_categories"))
    return {
        "id": str(raw.get("id") or "").strip(),
        "scheme_name": (raw.get("scheme_name") or "").strip(),
        "aliases": _list(raw.get("aliases")),
        "category": category,
        "additional_categories": extra,
        "categories": list(dict.fromkeys(([category] if category else []) + extra)),
        "level": raw.get("level"),
        "applicable_state": raw.get("applicable_state"),
        "department": raw.get("department") or raw.get("ministry"),
        "short_description": raw.get("short_description"),
        "detailed_description": raw.get("detailed_description"),
        "eligibility": _list(raw.get("eligibility")),
        "min_age": _num(raw.get("min_age")),
        "max_age": _num(raw.get("max_age")),
        "gender": raw.get("gender"),
        "social_categories": _list(raw.get("social_categories")) or None,
        "income_limit_annual": _num(raw.get("income_limit_annual")),
        "income_limit": raw.get("income_limit"),
        "occupations": [o.lower() for o in _list(raw.get("occupations"))] or None,
        "min_education": raw.get("min_education"),
        "land_required": raw.get("land_required"),
        "area": (str(raw.get("area")).capitalize() if str(raw.get("area") or "").capitalize() in ("Rural", "Urban") else None),
        "bpl_required": True if raw.get("bpl_required") else None,
        "minority_required": True if raw.get("minority_required") else None,
        "disability_required": True if raw.get("disability_required") else None,
        "ex_serviceman_required": True if raw.get("ex_serviceman_required") else None,
        "benefits": raw.get("benefits"),
        "required_documents": _list(raw.get("required_documents")),
        "application_process": _list(raw.get("application_process")),
        "deadline": raw.get("deadline"),
        "official_url": raw.get("official_url"),
        "source_url": raw.get("source_url"),
        "source_document": raw.get("source_document"),
        "last_verified": raw.get("last_verified"),
        "status": raw.get("status") or "verification_required",
        "rules_complete": bool(raw.get("rules_complete", False)),
    }


@lru_cache(maxsize=1)
def _scan() -> tuple:
    records, errors, failed = [], [], []
    seen_ids, seen_names = set(), set()
    if db_config.CATALOG_DIR.exists():
        for path in sorted(db_config.CATALOG_DIR.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{path.name}: invalid JSON ({exc})")
                failed.append(path.name)
                continue
            items = data.get("schemes", []) if isinstance(data, dict) else data
            for i, raw in enumerate(items, start=1):
                rec = normalize_record(raw)
                rec["_file"] = path.name
                label = f"{path.name} #{i} ({rec['scheme_name'] or 'no name'})"
                if not rec["id"] or not rec["scheme_name"]:
                    errors.append(f"{label}: missing 'id' or 'scheme_name' - skipped")
                    continue
                name_key = (norm(rec["scheme_name"]), norm(rec["applicable_state"] or ""))
                if rec["id"] in seen_ids or name_key in seen_names:
                    errors.append(f"{label}: duplicate scheme - skipped")
                    continue
                seen_ids.add(rec["id"])
                seen_names.add(name_key)
                records.append(rec)
    return tuple(records), tuple(errors), tuple(failed)


@lru_cache(maxsize=1)
def _by_id() -> dict:
    return {r["id"]: r for r in _scan()[0]}


def reload_catalog() -> None:
    _scan.cache_clear()
    _by_id.cache_clear()


def load_catalog() -> list[dict]:
    return list(_scan()[0])


def load_catalog_with_errors() -> tuple[list[dict], list[str], list[str]]:
    records, errors, failed = _scan()
    return list(records), list(errors), list(failed)


def get_by_id(scheme_id: str) -> dict | None:
    return _by_id().get(scheme_id)


def find_scheme(name: str) -> dict | None:
    target = norm(name)
    if not target:
        return None
    records = _scan()[0]
    for rec in records:
        if target in {norm(n) for n in [rec["scheme_name"]] + rec["aliases"]}:
            return rec
    for rec in records:
        for n in [rec["scheme_name"]] + rec["aliases"]:
            n = norm(n)
            if len(n) >= 6 and (n in target or target in n):
                return rec
    return None


def record_hash(rec: dict) -> str:
    clean = {k: v for k, v in rec.items() if not k.startswith("_")}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()


def flags(categories: list[str]) -> dict:
    return {f"cat_{slug}": (cat in categories) for cat, slug in db_config.CATEGORY_SLUGS.items()}


def make_metadata(*, scheme_id, scheme_name, categories, level, state, department, official_url,
                  source_url, source_document, last_verified, status, doc_type, page=0, source="") -> dict:
    """Flat metadata for ChromaDB (no lists, no None)."""
    meta = {
        "scheme_id": scheme_id, "scheme_name": scheme_name,
        "category": categories[0] if categories else "",
        "level": level or "Unknown", "is_central": level == "Central",
        "state": state or "", "department": department or "",
        "official_url": official_url or "", "source_url": source_url or "",
        "source_document": source_document or "", "last_verified": last_verified or "",
        "status": status or "verification_required", "doc_type": doc_type,
        "page": page, "source": source,
    }
    meta.update(flags(categories))
    return meta


def record_metadata(rec: dict) -> dict:
    return make_metadata(
        scheme_id=rec["id"], scheme_name=rec["scheme_name"], categories=rec["categories"],
        level=rec["level"], state=rec["applicable_state"], department=rec["department"],
        official_url=rec["official_url"], source_url=rec["source_url"],
        source_document=rec["source_document"], last_verified=rec["last_verified"],
        status=rec["status"], doc_type="catalog", source=rec.get("_file", "catalog"),
    )


def _lines(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else NOT_STATED


def _v(value) -> str:
    return str(value) if value not in (None, "") else NOT_STATED


def record_text(rec: dict) -> str:
    """Searchable text for one scheme (used for embeddings)."""
    return (
        f"Scheme name: {rec['scheme_name']}\n"
        f"Also known as: {', '.join(rec['aliases']) or '-'}\n"
        f"Categories: {', '.join(rec['categories']) or NOT_STATED}\n"
        f"Central or State scheme: {_v(rec['level'])}\n"
        f"Applicable state: {_v(rec['applicable_state'])}\n"
        f"Department: {_v(rec['department'])}\n"
        f"Description: {_v(rec['short_description'] or rec['detailed_description'])}\n"
        f"Eligibility conditions:\n{_lines(rec['eligibility'])}\n"
        f"Income limit: {_v(rec['income_limit'])}\n"
        f"Benefits: {_v(rec['benefits'])}\n"
        f"Required documents:\n{_lines(rec['required_documents'])}\n"
        f"Application process:\n{_lines(rec['application_process'])}\n"
        f"Status: {rec['status']}"
    )