"""One-time upgrade of data/catalog/schemes.json to the new record format.
Run:  python -m scripts.upgrade_catalog
Safe to run twice. A backup (schemes.json.bak) is created. Existing values are never overwritten.
Structured rules are added ONLY where the record's own text already states them."""
import json
import shutil

import db_config

FILE = db_config.CATALOG_DIR / "schemes.json"

NEW_FIELDS = {
    "additional_categories": [], "short_description": None, "detailed_description": None,
    "min_age": None, "max_age": None, "gender": None, "social_categories": None,
    "income_limit_annual": None, "occupations": None, "min_education": None, "land_required": None,
    "source_url": None, "status": "verification_required", "rules_complete": False,
    "area": None, "bpl_required": None, "minority_required": None,
    "disability_required": None, "ex_serviceman_required": None,
}
# Taken from text already present in the starter records (ages, gender, occupation, land).
KNOWN_RULES = {
    "pmmvy": {"gender": "Female", "min_age": 19},
    "pm-vishwakarma": {"min_age": 18},
    "pmegp": {"min_age": 18},
    "pm-kisan": {"occupations": ["farmer", "agricultur", "cultivat"], "land_required": True},
    "pm-yasasvi": {"additional_categories": ["Education"]},
    # rural / urban taken from the applicable_state text already in these records
    "pmay-urban": {"area": "Urban"},
    "pmay-gramin": {"area": "Rural"},
    "vb-g-ram-g": {"area": "Rural"},
}


def main() -> None:
    if not FILE.exists():
        print("data/catalog/schemes.json not found - nothing to upgrade.")
        return
    data = json.loads(FILE.read_text(encoding="utf-8"))
    shutil.copy(FILE, FILE.with_suffix(".json.bak"))
    changed = 0
    for rec in data.get("schemes", []):
        for key, default in NEW_FIELDS.items():
            if key not in rec:
                rec[key] = default
                changed += 1
        for key, value in KNOWN_RULES.get(rec.get("id"), {}).items():
            if rec.get(key) in (None, [], False):
                rec[key] = value
                changed += 1
    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Upgraded {len(data.get('schemes', []))} records ({changed} fields added). Backup: schemes.json.bak")


if __name__ == "__main__":
    main()