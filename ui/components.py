"""Reusable Streamlit components: scheme cards and result rendering."""
import streamlit as st

import db_config
from backend import auth

STATUS_STYLE = {
    "eligible": ("✅ Eligible", "#16a34a"),
    "potentially_eligible": ("🟡 Possibly eligible", "#d97706"),
    "insufficient_information": ("ℹ️ Insufficient information", "#6b7280"),
    "ineligible": ("❌ Not eligible", "#dc2626"),
}
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
    with st.container(border=True):
        st.markdown(f"### {card['scheme_name']}")
        tags = f'<span class="badge" style="background:{color}">{label}</span>'
        for cat in card.get("categories") or ([card["category"]] if card.get("category") else []):
            tags += f'<span class="tag">{cat}</span>'
        if card.get("scheme_level"):
            tags += f'<span class="tag">{card["scheme_level"]} scheme</span>'
        if details.get("scheme_status") and details["scheme_status"] != "active":
            tags += f'<span class="tag">{details["scheme_status"].replace("_", " ")}</span>'
        st.markdown(tags, unsafe_allow_html=True)

        if card.get("description"):
            st.write(card["description"])
        if card.get("explanation"):
            st.info(card["explanation"])

        c1, c2 = st.columns(2)
        with c1:
            _fact("Government department", card.get("department"))
            _fact("Applicable state / UT", card.get("applicable_state"))
        with c2:
            _fact("Main benefits", card.get("benefits"))
            _fact("Income limit", card.get("income_limit"))

        criteria = card.get("eligibility_criteria") or []
        st.markdown("**Eligibility summary**")
        if criteria:
            st.markdown(_bullets(criteria[:3]) + (f"\n- _…and {len(criteria) - 3} more (see full details)_" if len(criteria) > 3 else ""))
        else:
            st.caption("Eligibility conditions are not officially verified yet - check the official portal.")

        if card.get("reasons"):
            st.markdown("**Why this status**")
            st.markdown(_bullets(card["reasons"]))
        if card.get("missing_information"):
            st.warning("Information needed: " + "; ".join(card["missing_information"]))

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
            if details.get("rules"):
                st.markdown("**Rules used for the automatic check**")
                st.markdown(_bullets(details["rules"]))
            if criteria:
                st.markdown("**All eligibility conditions**")
                st.markdown(_bullets(criteria))
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Required documents**")
                docs = app.get("required_documents") or []
                st.markdown(_bullets(docs) if docs else "_Not officially verified - check the portal._")
            with d2:
                st.markdown("**Application process**")
                steps = app.get("application_steps") or []
                st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) if steps
                            else "_Not officially verified - check the portal._")
            st.markdown("**Deadline:** " + (app.get("deadline") or "Not verified"))
            if app.get("notes"):
                st.caption(app["notes"])
            if details.get("source_url"):
                st.markdown(f"**Official source page:** {details['source_url']}")

        link = app.get("official_link")
        b1, b2, _ = st.columns([2, 2, 3])
        if link:
            b1.link_button("🌐 Official application link", link)
        if user and card["status"] != "ineligible":
            if b2.button("💾 Save to My Applications", key=f"save_{key}"):
                auth.save_application(user["email"], card["scheme_name"], link)
                st.toast("Saved. Track your progress in the sidebar.", icon="✅")


def render_result(result: dict, key: str, limit: int | None = None) -> None:
    if result.get("error"):
        st.error(result["error"])
        return
    if result["message"]:
        st.markdown(result["message"])
    cards = result["cards"]
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