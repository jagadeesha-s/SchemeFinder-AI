"""Check every record in data/catalog/*.json.   Run:  python -m scripts.validate_catalog"""
import re
import sys
from collections import Counter
from urllib.parse import urlparse

import db_config
from backend.catalog import load_catalog_with_errors

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(db_config.OFFICIAL_SUFFIXES)


def main() -> int:
    records, load_errors, _ = load_catalog_with_errors()
    errors, warnings = list(load_errors), []

    for r in records:
        tag = f"{r['_file']}:{r['id']}"
        if not r["categories"]:
            errors.append(f"{tag}: no category")
        for c in r["categories"]:
            if c not in db_config.CATEGORIES:
                errors.append(f"{tag}: unknown category '{c}'")
        if r["level"] not in db_config.LEVELS:
            errors.append(f"{tag}: level must be one of {db_config.LEVELS}")
        if r["level"] in ("State", "UT") and not r["applicable_state"]:
            errors.append(f"{tag}: State/UT scheme needs applicable_state")
        if r["status"] not in db_config.STATUSES:
            errors.append(f"{tag}: status must be one of {db_config.STATUSES}")
        if r["last_verified"] and not DATE_RE.match(str(r["last_verified"])):
            errors.append(f"{tag}: last_verified must be YYYY-MM-DD")
        if r["rules_complete"] and not r["last_verified"]:
            errors.append(f"{tag}: rules_complete is true but last_verified is empty")
        if r["min_education"] and r["min_education"] not in db_config.EDUCATION_ORDER:
            errors.append(f"{tag}: min_education must be one of {db_config.EDUCATION_ORDER}")
        for field in ("official_url", "source_url"):
            url = r[field]
            if url:
                if not url.startswith("https://"):
                    warnings.append(f"{tag}: {field} should start with https://")
                elif not host_ok(url):
                    warnings.append(f"{tag}: {field} is not on a typical government domain - check it is official")
        if not (r["official_url"] or r["source_url"]):
            warnings.append(f"{tag}: no official URL")
        if not r["last_verified"]:
            warnings.append(f"{tag}: not verified yet (last_verified empty)")

    print(f"Valid scheme records: {len(records)}")
    print("By category :", dict(Counter(c for r in records for c in r["categories"])))
    print("By level    :", dict(Counter(r["level"] for r in records)))
    print("Verified    :", sum(1 for r in records if r["last_verified"]), "of", len(records))
    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR  :", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())