"""One-time upgrade: adds STRUCTURED rules to the scholarship records in data/catalog/schemes.json.
Run from the project root:   python -m scripts.upgrade_scholarship_rules

Only rules that the record's OWN text already states are added (all five say 'students'; CSSS names Class 12).
Nothing is overwritten, a backup (schemes.json.bak2) is made, and it is safe to run twice.
Income limits, categories and amounts are NOT added here - add them from the official scholarship guidelines."""
import json
import shutil

import db_config

FILE = db_config.CATALOG_DIR / "schemes.json"
RULES = {
    "csss": {"occupations": ["student"], "min_education": "12th pass"},    # "Class 12 ... pursuing regular courses"
    "nsp": {"occupations": ["student"]},
    "ssp-karnataka": {"occupations": ["student"]},                         # "Karnataka domicile students"
    "pm-usp": {"occupations": ["student"]},                                # "Domicile students of J&K and Ladakh"
    "pm-yasasvi": {"occupations": ["student"]},                            # "Students belonging to OBC, EBC and DNT"
}


def main() -> None:
    data = json.loads(FILE.read_text(encoding="utf-8"))
    shutil.copy(FILE, FILE.with_suffix(".json.bak2"))
    changed = 0
    for rec in data.get("schemes", []):
        for key, value in RULES.get(rec.get("id"), {}).items():
            if rec.get(key) in (None, [], ""):
                rec[key] = value
                changed += 1
    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Added {changed} rule field(s). Backup saved as schemes.json.bak2")


if __name__ == "__main__":
    main()