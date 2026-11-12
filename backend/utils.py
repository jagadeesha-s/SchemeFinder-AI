"""Small shared helpers."""
import re

import config


def norm(name: str) -> str:
    """Normalise a scheme name for matching across agents."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def clean_profile(profile: dict | None) -> dict:
    """Keep only known keys, drop empty values, coerce numbers."""
    out: dict = {}
    for key in config.PROFILE_KEYS:
        value = (profile or {}).get(key)
        if value is None or str(value).strip().lower() in ("", "null", "none", "select..."):
            continue
        if key == "age":
            try:
                value = int(float(value))
            except (TypeError, ValueError):
                continue
        elif key == "annual_income":
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
        else:
            value = str(value).strip()
        out[key] = value
    return out


def missing_fields(profile: dict) -> list[str]:
    return [f for f in config.REQUIRED_PROFILE_FIELDS if f not in profile]


def find_urls(text: str) -> set[str]:
    return {u.rstrip(".,;)") for u in re.findall(r"https?://[^\s\"'<>]+", text or "")}
