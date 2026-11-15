"""Reusable Streamlit components: scheme cards, summary counts, result filters."""
import streamlit as st

import db_config
from backend import auth
from backend.utils import norm

STATUS_STYLE = {
    "eligible": ("✅ Eligible", "#16a34a"),
    "potentially_eligible": ("🟡 Possibly eligible", "#d97706"),
    "insufficient_information": ("ℹ️ Needs more information", "#6b7280"),
    "ineligible": ("❌ Not eligible", "#dc2626"),
}
RESULT_ICON = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "UNKNOWN": "❔ UNKNOWN"}
NOT_STATED = "Not officially verified"


def _fact(label: str, value) -> None:
    st.markdown(
        f'<div class="fact-label">{label}</div><div class="fact-value">{value or NOT_STATED}</div>',
        unsafe_allow_html=True,
    )


def source_line(src: dict) -> str:
    label = src.get("source_document") or src["file"]
    if src.get("page"):
        label += f", page {src['page']}"
    return f"[{label}]({src['official_url']})" if src.get("official_url") else label


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items)


def render_card(card: dict, key: str) -> None:
    label, color = STATUS_STYLE.get(card["status"], STATUS_STYLE["insufficient_information"])
    user = st.session_state.get("user")
    app = card.get("application") or {}
    details = card.get("details") or {}
    conditions = card.get("conditions") or []
    with st.container(border=True):
        st.markdown(f"### {card['scheme_name']}")
        tags = f'<span class="badge" style="background:{color}">{label}</span>'
        for cat in card.get("categories") or ([card["category"]] if card.get("category") else []):
            tags += f'<span class="tag">{cat}</span>'
        if card.get("scheme_level"):
            tags += f'<span class="tag">{card["scheme_level"]} scheme</span>'
        st.markdown(tags, unsafe_allow_html=True)

        if card.get("relevance_reasons"):
            st.caption("Shown because: " + "; ".join(card["relevance_reasons"][:3]))
        if card.get("description"):
            st.write(card["description"])
        for w in card.get("verification_warnings") or []:
            st.warning(w)

        c1, c2 = st.columns(2)
        with c1:
            _fact("Government department", card.get("department"))
            _fact("Applicable state / UT", card.get("applicable_state"))
        with c2:
            _fact("Benefits", card.get("benefits"))
            _fact("Income limit", card.get("income_limit"))

        # ---- condition-by-condition result (this is where the profile is used)
        st.markdown("**Why this status** (official condition → your result)")
        if conditions:
            rows = []
            for c in conditions:
                opt = "" if c.get("mandatory", True) else " _(optional)_"
                rows.append(f"- **{c['name']}**{opt}: {c.get('requirement') or '-'} → "
                            f"{RESULT_ICON.get(c['result'], c['result'])} — {c['reason']}")
            st.markdown("\n".join(rows))
        else:
            st.caption("No eligibility conditions are officially recorded for this scheme yet.")
        if card.get("missing_information"):
            st.warning("Information needed: " + "; ".join(card["missing_information"]))
        if card.get("explanation"):
            st.info("AI explanation (not an official statement): " + card["explanation"])

        lv = card.get("last_verified")
        st.markdown(
            "**Sources:** " + " · ".join(source_line(s) for s in card["sources"])
            + " &nbsp;|&nbsp; **Last verified:** "
            + (lv if lv else '<span class="unverified">Not yet verified - confirm on the official portal</span>'),
            unsafe_allow_html=True,
        )

        with st.expander("📄 View full details"):
            if details.get("detailed_description"):
                st.write(details["detailed_description"])
            if details.get("aliases"):
                st.markdown("**Also known as:** " + ", ".join(details["aliases"]))
            if card.get("eligibility_criteria"):
                st.markdown("**Official eligibility conditions**")
                st.markdown(_bullets(card["eligibility_criteria"]))
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Required documents**")
                docs = app.get("required_documents") or []
                st.markdown(_bullets(docs) if docs else "_Not officially verified - check the portal._")
            with d2:
                st.markdown("**Application steps**")
                steps = app.get("application_steps") or []
                st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) if steps
                            else "_Not officially verified - check the portal._")
            st.markdown("**Deadline:** " + (app.get("deadline") or "Not verified"))
            if app.get("notes"):
                st.caption(app["notes"])
            if app.get("official_link"):
                st.markdown(f"**Official application URL:** {app['official_link']}")
            if card.get("source_url"):
                st.markdown(f"**Official source URL:** {card['source_url']}")

        link = app.get("official_link")
        b1, b2, _ = st.columns([2, 2, 3])
        if link:
            b1.link_button("🌐 Official application link", link)
        if user and card["status"] != "ineligible":
            if b2.button("💾 Save to My Applications", key=f"save_{key}"):
                auth.save_application(user["email"], card["scheme_name"], link)
                st.toast("Saved. Track your progress in the sidebar.", icon="✅")


# ------------------------------------------------------------------ filters
def _state_matches(card: dict, chosen: str) -> bool:
    applicable = card.get("applicable_state") or ""
    if chosen == "All India schemes":
        return not applicable or norm(applicable).startswith("all india")
    return norm(chosen) in norm(applicable) or norm(applicable).startswith("all india") or not applicable


def _filter_cards(cards: list[dict], key: str) -> list[dict]:
    labels = {v[0]: k for k, v in STATUS_STYLE.items()}
    f1, f2, f3 = st.columns(3)
    chosen_status = f1.multiselect("Eligibility status", list(labels), default=list(labels), key=f"fs_{key}")
    cats = sorted({c for card in cards for c in (card.get("categories") or [])})
    chosen_cat = f2.selectbox("Category", ["All categories"] + cats, key=f"fc_{key}")
    states = sorted({(c.get("applicable_state") or "").strip() for c in cards
                     if c.get("applicable_state") and not norm(c["applicable_state"]).startswith("all india")})
    chosen_state = f3.selectbox("State / UT", ["All states", "All India schemes"] + states, key=f"fst_{key}")

    wanted = {labels[s] for s in chosen_status}
    out = [c for c in cards if c["status"] in wanted]
    if chosen_cat != "All categories":
        out = [c for c in out if chosen_cat in (c.get("categories") or [])]
    if chosen_state != "All states":
        out = [c for c in out if _state_matches(c, chosen_state)]
    return out


def _summary_bar(result: dict) -> None:
    counts = result.get("counts") or {}
    cols = st.columns(5)
    cols[0].metric("Schemes evaluated", result.get("evaluated", len(result["cards"])))
    cols[1].metric("Eligible", counts.get("eligible", 0))
    cols[2].metric("Possibly eligible", counts.get("potentially_eligible", 0))
    cols[3].metric("Need more info", counts.get("insufficient_information", 0))
    cols[4].metric("Not eligible", counts.get("ineligible", 0))


PROFILE_LABELS = {"age": "Age", "state": "State", "annual_income": "Income", "category": "Category",
                  "gender": "Gender", "occupation": "Occupation", "education": "Education", "land_owner": "Owns land"}


def render_result(result: dict, key: str, limit: int | None = None, filters: bool = False) -> None:
    if result.get("error"):
        st.error(result["error"])
        return
    for w in result.get("profile_warnings") or []:
        st.warning(w)
    used = result.get("profile_used") or {}
    if used:
        st.caption("Profile used for matching: " + ", ".join(
            f"{PROFILE_LABELS.get(k, k)} = {v}" for k, v in used.items()))
    if result["message"]:
        st.markdown(result["message"])
    cards = result["cards"]
    if cards and filters:
        _summary_bar(result)
        cards = _filter_cards(cards, key)
        st.caption(f"{len(cards)} scheme(s) match the filters below.")

    for i, card in enumerate(cards[:limit] if limit else cards):
        render_card(card, f"{key}_{i}")
    if limit and len(cards) > limit:
        st.caption(f"Showing {limit} of {len(cards)} schemes")
        if st.button("Show more schemes", key=f"more_{key}"):
            st.session_state["show_n"] = limit + db_config.CARDS_PER_PAGE
            st.rerun()
    if not cards and result["sources"]:
        st.markdown("**Sources:** " + " · ".join(source_line(s) for s in result["sources"]))
    if result["follow_up_questions"]:
        st.markdown("**To give you a more accurate answer, please tell me:**")
        st.markdown(_bullets(result["follow_up_questions"]))
    st.caption(result["disclaimer"])