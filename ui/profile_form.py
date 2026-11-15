"""The 'My Profile' section: structured form, dynamic fields, Save / Edit / Clear, completion bar.

State used
  st.session_state["saved_profile"]  the saved, cleaned profile (used by every search)
  st.session_state["profile_mode"]   "edit" or "view"
  st.session_state["pf_*"]           the form widgets (only exist while editing)
The saved profile lives in its own key, so changing the category, filters or mode never erases it."""
import streamlit as st

import db_config
from backend import auth
from backend.profile import (describe_profile, missing_required, normalize_profile, occupation_kind,
                             profile_completion)

SELECT = "Select..."


def ensure_loaded(user: dict) -> None:
    if "saved_profile" not in st.session_state:
        saved = auth.load_profile(user["email"])
        st.session_state["saved_profile"] = saved
        st.session_state["profile_mode"] = "view" if saved else "edit"


def _opt(value, options):
    return value if value in options else SELECT


def _prefill(saved: dict) -> None:
    """Copy the saved profile into the form widgets (called when Edit is pressed)."""
    ss = st.session_state
    ss["pf_age"] = saved.get("age")
    ss["pf_income"] = int(saved["annual_income"]) if saved.get("annual_income") is not None else None
    ss["pf_family"] = saved.get("family_size")
    ss["pf_district"] = saved.get("district", "")
    ss["pf_course"] = saved.get("course", "")
    ss["pf_land_acres"] = float(saved["land_acres"]) if saved.get("land_acres") is not None else None
    ss["pf_business_age"] = float(saved["business_age"]) if saved.get("business_age") is not None else None
    ss["pf_turnover"] = int(saved["turnover"]) if saved.get("turnover") is not None else None
    ss["pf_business_type"] = saved.get("business_type", "")
    pairs = {
        "pf_gender": ("gender", db_config.GENDERS), "pf_state": ("state", db_config.INDIAN_STATES),
        "pf_residence": ("residence", db_config.RESIDENCE), "pf_category": ("category", db_config.SOCIAL_CATEGORIES),
        "pf_education": ("education", db_config.EDUCATION_ORDER), "pf_studying": ("studying", db_config.YES_NO),
        "pf_year": ("study_year", db_config.STUDY_YEARS), "pf_institution": ("institution_type", db_config.INSTITUTION_TYPES),
        "pf_land_status": ("land_status", db_config.LAND_STATUS), "pf_irrigation": ("irrigation", db_config.IRRIGATION),
        "pf_employment": ("employment_status", db_config.EMPLOYMENT_STATUS), "pf_skill": ("skill_interest", db_config.YES_NO),
        "pf_disability": ("disability", db_config.YES_NO), "pf_marital": ("marital_status", db_config.MARITAL),
        "pf_bpl": ("bpl", db_config.YES_NO), "pf_minority": ("minority", db_config.YES_NO),
        "pf_community": ("minority_community", db_config.MINORITY_COMMUNITIES), "pf_exserv": ("ex_serviceman", db_config.YES_NO),
    }
    for key, (field, options) in pairs.items():
        ss[key] = _opt(saved.get(field), options)
    occ = saved.get("occupation", "")
    if occ.startswith("Other ("):
        ss["pf_occupation"], ss["pf_occupation_other"] = "Other", occ[7:-1]
    else:
        ss["pf_occupation"], ss["pf_occupation_other"] = _opt(occ, db_config.OCCUPATION_TYPES), ""


def _clear_form_keys() -> None:
    for key in [k for k in st.session_state if k.startswith("pf_")]:
        del st.session_state[key]


def _collect() -> dict:
    """Read the form widgets into a raw dict (validated afterwards by normalize_profile)."""
    ss = st.session_state

    def v(key):
        value = ss.get(key)
        return None if value in (None, "", SELECT) else value

    occupation = v("pf_occupation")
    if occupation == "Other" and (ss.get("pf_occupation_other") or "").strip():
        occupation = f"Other ({ss['pf_occupation_other'].strip()[:40]})"
    return {
        "age": v("pf_age"), "gender": v("pf_gender"), "state": v("pf_state"), "district": v("pf_district"),
        "residence": v("pf_residence"), "category": v("pf_category"), "annual_income": v("pf_income"),
        "family_size": v("pf_family"), "education": v("pf_education"), "studying": v("pf_studying"),
        "course": v("pf_course"), "study_year": v("pf_year"), "institution_type": v("pf_institution"),
        "occupation": occupation, "land_acres": v("pf_land_acres"), "land_status": v("pf_land_status"),
        "irrigation": v("pf_irrigation"), "business_type": v("pf_business_type"),
        "business_age": v("pf_business_age"), "turnover": v("pf_turnover"),
        "employment_status": v("pf_employment"), "skill_interest": v("pf_skill"),
        "disability": v("pf_disability"), "marital_status": v("pf_marital"), "bpl": v("pf_bpl"),
        "minority": v("pf_minority"), "minority_community": v("pf_community"), "ex_serviceman": v("pf_exserv"),
    }


def _completion_bar(profile: dict) -> None:
    comp = profile_completion(profile)
    st.progress(comp["percent"] / 100, text=f"Profile completion: {comp['percent']}%")
    if comp["missing_required"]:
        st.caption("Required: " + ", ".join(comp["missing_required"]))


def _edit_form(user: dict) -> None:
    ss = st.session_state
    sel = lambda opts: [SELECT] + list(opts)          # noqa: E731

    st.markdown("##### 🧑 PERSONAL INFORMATION")
    c1, c2, c3 = st.columns(3)
    c1.number_input("Age *", min_value=0, max_value=120, value=None, step=1, key="pf_age", placeholder="e.g. 28")
    c2.selectbox("Gender *", sel(db_config.GENDERS), key="pf_gender")
    c3.selectbox("State / Union Territory *", sel(db_config.INDIAN_STATES), key="pf_state")
    c1, c2, c3 = st.columns(3)
    c1.text_input("District (optional)", key="pf_district", max_chars=60)
    c2.selectbox("Rural or urban residence (optional)", sel(db_config.RESIDENCE), key="pf_residence")
    c3.selectbox("Social category *", sel(db_config.SOCIAL_CATEGORIES), key="pf_category")
    c1, c2, _ = st.columns(3)
    c1.number_input("Annual family income (₹) *", min_value=0, value=None, step=10000, key="pf_income",
                    placeholder="e.g. 250000")
    c2.number_input("Number of family members (optional)", min_value=1, max_value=30, value=None, step=1,
                    key="pf_family")

    occupation_now = ss.get("pf_occupation")            # value from the previous run (drives dynamic fields)
    kind = occupation_kind(occupation_now if occupation_now != "Other" else "")

    st.markdown("##### 🎓 EDUCATION")
    c1, c2, _ = st.columns(3)
    c1.selectbox("Highest education completed *", sel(db_config.EDUCATION_ORDER), key="pf_education")
    c2.selectbox("Currently studying?", sel(db_config.YES_NO), key="pf_studying")
    if ss.get("pf_studying") == "Yes" or kind == "student":
        c1, c2, c3 = st.columns(3)
        c1.text_input("Course or degree", key="pf_course", placeholder="e.g. B.E. Computer Science", max_chars=80)
        c2.selectbox("Current year of study", sel(db_config.STUDY_YEARS), key="pf_year")
        c3.selectbox("College / institution type", sel(db_config.INSTITUTION_TYPES), key="pf_institution")

    st.markdown("##### 💼 OCCUPATION")
    c1, c2, _ = st.columns(3)
    c1.selectbox("Occupation *", sel(db_config.OCCUPATION_TYPES), key="pf_occupation")
    if ss.get("pf_occupation") == "Other":
        c2.text_input("Please specify", key="pf_occupation_other", max_chars=40)
    if kind == "farmer":
        c1, c2, c3 = st.columns(3)
        c1.number_input("Landholding (acres)", min_value=0.0, max_value=100000.0, value=None, step=0.5, key="pf_land_acres")
        c2.selectbox("Land ownership status", sel(db_config.LAND_STATUS), key="pf_land_status")
        c3.selectbox("Irrigation available?", sel(db_config.IRRIGATION), key="pf_irrigation")
    elif kind == "business":
        c1, c2, c3 = st.columns(3)
        c1.selectbox("Business type", sel(db_config.BUSINESS_TYPES), key="pf_business_type")
        c2.number_input("Business age (years)", min_value=0.0, max_value=100.0, value=None, step=0.5, key="pf_business_age")
        c3.number_input("Annual turnover (₹)", min_value=0, value=None, step=50000, key="pf_turnover")
    elif kind == "unemployed":
        c1, c2, _ = st.columns(3)
        c1.selectbox("Employment status", sel(db_config.EMPLOYMENT_STATUS), key="pf_employment")
        c2.selectbox("Interested in skill training?", sel(db_config.YES_NO), key="pf_skill")

    st.markdown("##### ➕ ADDITIONAL INFORMATION (optional)")
    ynp = lambda opts: [SELECT] + list(opts) + ["Prefer not to say"]      # noqa: E731
    c1, c2, c3 = st.columns(3)
    c1.selectbox("Disability status", ynp(db_config.YES_NO), key="pf_disability")
    c2.selectbox("Marital status", ynp(db_config.MARITAL), key="pf_marital")
    c3.selectbox("BPL (Below Poverty Line) family", ynp(db_config.YES_NO), key="pf_bpl")
    c1, c2, c3 = st.columns(3)
    c1.selectbox("Minority community", ynp(db_config.YES_NO), key="pf_minority")
    if ss.get("pf_minority") == "Yes":
        c2.selectbox("Which community?", sel(db_config.MINORITY_COMMUNITIES), key="pf_community")
    c3.selectbox("Ex-serviceman", ynp(db_config.YES_NO), key="pf_exserv")

    live, live_warnings = normalize_profile(_collect())
    _completion_bar(live)
    st.caption("* required. We never ask for Aadhaar, bank account numbers or passwords. Optional answers are used "
               "only to check scheme conditions; choose 'Prefer not to say' to skip any of them.")

    b1, b2, b3, _ = st.columns([1.2, 1, 1, 3])
    if b1.button("💾 Save Profile", type="primary", key="pf_save"):
        if live_warnings:
            for w in live_warnings:
                st.error(w)
        missing = missing_required(live)
        if missing:
            st.error("Please fill in: " + ", ".join(missing))
        elif not live_warnings:
            auth.save_profile(user["email"], live)
            ss["saved_profile"] = live
            ss["profile_mode"] = "view"
            ss.pop("last_result", None)
            st.rerun()
    if ss.get("saved_profile") and b2.button("Cancel", key="pf_cancel"):
        _clear_form_keys()
        ss["profile_mode"] = "view"
        st.rerun()
    if b3.button("🗑️ Clear Profile", key="pf_clear"):
        _clear_profile(user)


def _clear_profile(user: dict) -> None:
    auth.delete_profile(user["email"])
    _clear_form_keys()
    st.session_state["saved_profile"] = {}
    st.session_state["profile_mode"] = "edit"
    st.session_state.pop("last_result", None)
    st.rerun()


def _view(user: dict) -> bool:
    saved = st.session_state["saved_profile"]
    _completion_bar(saved)
    groups = describe_profile(saved)
    cols = st.columns(max(len(groups), 1))
    for col, (group, rows) in zip(cols, groups.items()):
        with col:
            st.markdown(f"**{group}**")
            st.markdown("\n".join(f"- {label}: **{value}**" for label, value in rows))
    b1, b2, b3, _ = st.columns([1.4, 1, 1, 3])
    find = b1.button("🔎 Find My Schemes", type="primary", key="pf_find")
    if b2.button("✏️ Edit Profile", key="pf_edit"):
        _prefill(saved)
        st.session_state["profile_mode"] = "edit"
        st.rerun()
    if b3.button("🗑️ Clear Profile", key="pf_clear_view"):
        _clear_profile(user)
    return find


def render_profile_section(user: dict) -> tuple[dict, bool]:
    """Draws the section. Returns (saved profile, 'Find My Schemes' clicked)."""
    ensure_loaded(user)
    st.markdown('<div class="section-title">My Profile – Find Government Schemes for Me</div>', unsafe_allow_html=True)
    find = False
    with st.container(border=True):
        if st.session_state["profile_mode"] == "edit":
            _edit_form(user)
        else:
            find = _view(user)
    return st.session_state["saved_profile"], find