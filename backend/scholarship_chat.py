"""Scholarship chat engine - answers scholarship questions from YOUR scheme database only.

Why it is built this way
  * Replies about scholarships are written by plain Python from the catalog records and the rule engine
    (backend/rules.py). No AI model writes scholarship facts, so nothing can be invented.
  * Anything that is not about scholarships returns None, and the app hands the message to the existing
    Gemini pipeline (orchestrator.handle).

What it understands (simple English, small typos allowed)
  "list all scholarships"                      -> every scholarship in the database
  "scholarships for me" / "which can I get?"   -> checked against your saved profile
  "I am a 20 year old SC girl from Karnataka, family income 1.5 lakh, any scholarship?"
                                               -> details in the message are used for this question
  "documents for NSP" / "how to apply for CSSS" / "am I eligible for PM YASASVI?"  -> that scholarship"""
import difflib
import json
import re

import config
import db_config
from backend.catalog import load_catalog
from backend.profile import normalize_education, normalize_profile
from backend.rules import MISSING_QUESTIONS, STATUS_ORDER, build_card
from backend.utils import norm

SCHOLAR_RE = re.compile(r"scholar|stipend|fellowship", re.I)
SCHOLAR_WORDS = ("scholarship", "scholarships", "stipend", "stipends", "fellowship", "fellowships")
STATUS_LABEL = {
    "eligible": "✅ Eligible",
    "potentially_eligible": "🟡 Possibly eligible",
    "insufficient_information": "ℹ️ Needs more information",
    "ineligible": "❌ Not eligible",
}
PROFILE_LABELS = {"age": "Age", "state": "State", "category": "Category", "gender": "Gender",
                  "annual_income": "Income", "occupation": "Occupation", "education": "Education"}


# ------------------------------------------------------------ scholarship data
def is_scholarship(rec: dict) -> bool:
    """A scheme is a scholarship when its NAME says so, or it is an education / SC-ST-OBC welfare scheme whose
    description says so. (A skills scheme that merely pays a 'stipend' is not a scholarship.)"""
    if SCHOLAR_RE.search(rec["scheme_name"] + " " + " ".join(rec["aliases"])):
        return True
    if any(c in ("Education", "SC/ST/OBC Welfare") for c in rec["categories"]):
        text = " ".join([rec.get("short_description") or "", rec.get("benefits") or "", " ".join(rec["eligibility"])])
        return bool(re.search(r"scholar|fellowship", text, re.I))
    return False


def scholarship_records() -> list[dict]:
    return [r for r in load_catalog() if is_scholarship(r) and r["status"] not in ("closed", "discontinued")]


def document_scholarships() -> list[dict]:
    """Scholarships described only in data/schemes/sources.json (PDF/TXT documents you added).
    Their eligibility is NOT machine-checked, so they are listed separately."""
    try:
        data = json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for key, entry in data.items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        name = entry.get("scheme_name") or ""
        if SCHOLAR_RE.search(name):
            out.append({"name": name, "department": entry.get("department"), "url": entry.get("official_url"),
                        "state": entry.get("applicable_state"), "file": key})
    return out


# -------------------------------------------------------- reading the message
def _tokens(low: str) -> list[str]:
    return re.findall(r"[a-z]+", low)


def mentions_scholarship(low: str) -> bool:
    for tok in _tokens(low):
        if tok.startswith("scholar") or tok.startswith("stipend") or tok.startswith("fellowship"):
            return True
        if len(tok) >= 6 and difflib.get_close_matches(tok, SCHOLAR_WORDS, n=1, cutoff=0.78):
            return True            # typos such as "scolarship" or "scholership"
    return False


def wants_all(low: str) -> bool:
    return bool(re.search(r"\b(list|show|give|display|tell|see)\b.*\ball\b|\ball\b.*\bscholar|\bevery\b|"
                          r"\b(complete|full|entire)\s+list\b|\bavailable\s+scholar", low))


def wants_not_eligible(low: str) -> bool:
    return bool(re.search(r"not eligible|ineligible|including (the )?(ones|schemes)|even if", low))


def is_greeting(low: str) -> bool:
    return bool(re.fullmatch(r"\s*(hi|hello|hey|hii+|good (morning|afternoon|evening)|namaste|help|thanks|thank you)[\s!.?]*", low)) \
        or bool(re.search(r"what can you (do|help)|how (do|does) (this|it) work", low))


def find_named(low: str, recs: list[dict]) -> list[dict]:
    """Scholarships named in the message (by name or short name such as NSP / CSSS / PM YASASVI)."""
    msg = " " + norm(low) + " "
    found = []
    for rec in recs:
        for name in [rec["scheme_name"]] + rec["aliases"]:
            n = norm(name)
            if len(n) >= 3 and f" {n} " in msg:
                found.append(rec)
                break
    return found


def extract_details(text: str) -> dict:
    """Personal details typed in the message (used for this question only; validated by normalize_profile)."""
    low = text.lower()
    out: dict = {}

    m = (re.search(r"\b(?:i am|i'm|im|age(?: is)?|aged)\s*(?:a|an)?\s*(\d{1,2})\b(?!\s*(?:th|st|nd|rd|%|percent|lakh))", low)
         or re.search(r"\b(\d{1,2})\s*(?:years?|yrs?)\s*(?:old)?\b", low) or re.search(r"\b(\d{1,2})\s*y/?o\b", low))
    if m:
        out["age"] = int(m.group(1))

    for state in sorted(db_config.INDIAN_STATES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(state.lower()) + r"\b", low):
            out["state"] = state
            break

    if re.search(r"\bscheduled caste\b|\bsc\b", low):
        out["category"] = "SC"
    elif re.search(r"\bscheduled tribe\b|\bst\b(?!\s*(?:year|sem))", low):
        out["category"] = "ST"
    elif re.search(r"\bobc\b|\bbackward class", low):
        out["category"] = "OBC"
    elif re.search(r"\bews\b|economically weaker", low):
        out["category"] = "EWS"
    elif re.search(r"\bgeneral (?:category|caste|candidate)\b", low):
        out["category"] = "General"

    if re.search(r"\b(girl|woman|women|female|lady|daughter)\b", low):
        out["gender"] = "Female"
    elif re.search(r"\b(boy|man|male|son)\b", low):
        out["gender"] = "Male"

    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs)\b", low)
    if m:
        out["annual_income"] = float(m.group(1)) * 100000
    else:
        m = (re.search(r"(?:income|earn\w*|salary)\D{0,25}?(?:₹|rs\.?|inr)?\s*([\d,]{5,})", low)
             or re.search(r"(?:₹|rs\.?|inr)\s*([\d,]{5,})", low))
        if m:
            out["annual_income"] = float(m.group(1).replace(",", ""))

    if re.search(r"\b(student|studying|pursuing|college|university)\b", low):
        out["occupation"] = "Student"
        out["studying"] = "Yes"
    m = re.search(r"\b(?:completed|passed|finished|have|having|done)\s+(?:my\s+)?(10th|12th|diploma|iti|graduation|degree|post.?graduation)", low)
    if m:
        edu = normalize_education(m.group(1))
        if edu:
            out["education"] = edu
    return out


# ------------------------------------------------------------------- replies
def _level(rec: dict) -> str:
    if rec.get("level") == "Central":
        return "Central scheme"
    return f"{rec.get('applicable_state') or rec.get('level') or 'State'} scheme"


def _short(text: str | None, n: int = 150) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _why(card: dict) -> str:
    """The most important reason: a failed condition first, then what is unknown."""
    conds = [c for c in card["conditions"] if c["name"] != "Other official conditions"]
    for wanted in ("FAIL", "UNKNOWN"):
        hit = next((c for c in conds if c["result"] == wanted), None)
        if hit:
            return hit["reason"]
    return ""


def _line(rec: dict, card: dict | None, profile: dict | None = None) -> str:
    label = STATUS_LABEL[card["status"]] if card else ""
    head = f"- **{rec['scheme_name']}** — {_level(rec)}" + (f" — {label}" if label else "")
    bits = []
    if rec.get("benefits"):
        bits.append(f"Benefits: {_short(rec['benefits'])}")
    if rec["eligibility"]:
        bits.append(f"Official conditions: {_short('; '.join(rec['eligibility']))}")
    if card and _why(card):
        bits.append(f"Your profile: {_why(card)}")
    note = _community_note(rec, profile or {}) if card else ""
    if note:
        bits.append(f"⚠️ {note}")
    link = rec.get("official_url") or rec.get("source_url")
    bits.append(f"Official link: {link}" if link else "Official link: not available")
    return head + "".join(f"\n  - {b}" for b in bits)


def _profile_text(profile: dict) -> str:
    def show(key, value):
        return f"₹{int(value):,}" if key == "annual_income" else value
    return ", ".join(f"{PROFILE_LABELS[k]}: {show(k, profile[k])}" for k in PROFILE_LABELS
                     if profile.get(k) not in (None, ""))


COMMUNITY_PATTERNS = {
    "OBC": r"\bobc\b|backward class", "SC": r"\bscheduled castes?\b|\bsc\b", "ST": r"\bscheduled tribes?\b|\bst\b",
    "EWS": r"\bews\b|economically weaker", "Minority": r"\bminorit",
}


def _community_note(rec: dict, profile: dict) -> str:
    """Warning (not a rule): the official text names communities and the user's category is not among them."""
    mentioned = {name for name, pat in COMMUNITY_PATTERNS.items()
                 if re.search(pat, " ".join(rec["eligibility"] + [rec["scheme_name"]]).lower())}
    mine = profile.get("category")
    if mentioned and mine and mine not in mentioned:
        return (f"The official conditions mention {', '.join(sorted(mentioned))}; your saved category is {mine}, "
                "so this scholarship may not be meant for you - check the official text.")
    return ""


def _profile_for(rec: dict, profile: dict) -> dict:
    """A working student ('studying: Yes') still counts as a student for scholarships that need one."""
    if "student" in (rec.get("occupations") or []) and profile.get("studying") == "Yes":
        return {**profile, "occupation": "Student"}
    return profile


def _reply(kind, text, cards=None, show_cards=False, profile=None) -> dict:
    return {"kind": kind, "text": text, "cards": cards or [], "show_cards": show_cards, "profile_used": profile or {}}


def help_reply() -> dict:
    return _reply("help", (
        "Hi! I can help you find **scholarships** that match your profile. Try:\n"
        "- *List all scholarships*\n- *Which scholarships can I get?*\n"
        "- *I am a 20 year old SC student from Karnataka, family income 1.5 lakh - any scholarship for me?*\n"
        "- *What documents do I need for NSP?*\n\n"
        "For other schemes (farming, health, housing, business...) just ask - I will search the scheme database."))


def respond(message: str, saved_profile: dict | None) -> dict | None:
    """Returns a reply dict, or None when the message is not about scholarships."""
    text = (message or "").strip()
    if not text:
        return None
    low = text.lower()
    if is_greeting(low):
        return help_reply()

    recs = scholarship_records()
    named = find_named(low, recs)
    if not recs or not (named or mentions_scholarship(low)):
        return None

    details = extract_details(text)
    profile, _ = normalize_profile({**(saved_profile or {}), **details})
    has_profile = bool(profile)
    cards = {r["id"]: build_card(r, _profile_for(r, profile)) for r in recs}
    note_used = ""
    if details:
        note_used = "_Details taken from your message: " + _profile_text(normalize_profile(details)[0]) + "._\n\n"

    # ---------------------------------------------------- one named scholarship
    if named and not wants_all(low):
        rec = named[0]
        card = cards[rec["id"]]
        link = rec.get("official_url") or rec.get("source_url")
        lines = [f"**{rec['scheme_name']}** ({_level(rec)})"]
        asked_docs = re.search(r"document|papers|certificate", low)
        asked_apply = re.search(r"\bapply|application|how to|link|website|portal|deadline|last date", low)
        asked_benefit = re.search(r"benefit|amount|how much|money", low)
        if asked_docs:
            docs = rec["required_documents"]
            lines.append("**Required documents:** " + ("; ".join(docs) if docs else
                         "not verified in the database yet - please check the official portal."))
        if asked_apply:
            steps = rec["application_process"]
            lines.append("**How to apply:** " + (" → ".join(steps) if steps else "not verified in the database yet."))
            lines.append(f"**Deadline:** {rec.get('deadline') or 'not verified'}")
            lines.append(f"**Official link:** {link or 'not available'}")
        if asked_benefit or not (asked_docs or asked_apply):
            lines.append(f"**Benefits:** {rec.get('benefits') or 'not verified in the database yet.'}")
        if not (asked_docs or asked_apply) or re.search(r"eligib|qualify|can i|criteria|who can", low):
            lines.append(f"**Your result:** {STATUS_LABEL[card['status']]}" + (f" — {_why(card)}" if _why(card) else ""))
        note = _community_note(rec, profile)
        if note:
            lines.append(f"⚠️ {note}")
        if not rec.get("last_verified"):
            lines.append("⚠️ This record is not yet verified against the official source - confirm on the official portal.")
        return _reply("named", note_used + "\n\n".join(lines), [card], True, profile)

    # ------------------------------------------------------------ list / personal
    all_mode = wants_all(low)
    ordered = sorted(recs, key=lambda r: (STATUS_ORDER[cards[r["id"]]["status"]] if has_profile else 0, r["scheme_name"]))
    shown = ordered if (all_mode or wants_not_eligible(low) or not has_profile) \
        else [r for r in ordered if cards[r["id"]]["status"] != "ineligible"]
    hidden = len(ordered) - len(shown)

    if all_mode:
        intro = f"Here are **all {len(shown)} scholarships** in the database"
        intro += (" with your eligibility status:" if has_profile else ":")
    elif has_profile:
        intro = (f"I checked **{len(recs)} scholarships** against your details. "
                 f"**{len(shown)}** may suit you:" if shown else
                 f"I checked **{len(recs)} scholarships** against your details, and none of them matches the conditions recorded in the database.")
    else:
        intro = (f"There are **{len(recs)} scholarships** in the database. I do not have your details yet, so I cannot check "
                 "your eligibility - save your profile above, or tell me your age, state, category and family income.")
    body = [note_used + intro]
    body += [_line(r, cards[r["id"]] if has_profile else None, profile) for r in shown]
    if hidden:
        body.append(f"\n{hidden} scholarship(s) were hidden because your details do not meet a recorded condition "
                    "(for example your state). Say **'show not eligible too'** to see them.")

    docs = document_scholarships()
    if docs:
        body.append("\n**From your uploaded documents (eligibility is not checked automatically):**")
        body += [f"- {d['name']}" + (f" — {d['url']}" if d.get("url") else "") for d in docs]

    if any(not r.get("last_verified") for r in shown):
        body.append("\n⚠️ These records are not yet verified against the official source, and many do not list exact "
                    "income or category limits. Open the official link to confirm the rules before applying.")
    asks = []
    for r in shown:
        card = cards[r["id"]]
        if card["status"] != "ineligible":
            asks += [MISSING_QUESTIONS[f] for f in card["missing_fields"] if f in MISSING_QUESTIONS]
    asks = list(dict.fromkeys(asks))[:3]
    if asks and has_profile:
        body.append("\nTo check you more exactly, tell me: " + " ".join(asks))

    shown_cards = [cards[r["id"]] for r in shown] if has_profile else []
    return _reply("list" if all_mode else "personal", "\n".join(body), shown_cards, len(shown_cards) <= 3 and bool(shown_cards), profile)