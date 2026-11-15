"""Run from the project root:   python -m tests.test_profiles
Part A  logic tests with TEST-ONLY fake records (never added to your database)
Part B  the 4 sample profiles against YOUR real catalog (prints what is found and why)"""
from backend.catalog import normalize_record
from backend.profile import missing_required, normalize_profile, profile_completion
from backend.rules import evaluate, profile_categories, select_cards


def fake(**over):
    base = {"id": "t", "scheme_name": "TEST ONLY scheme", "category": "Education", "level": "Central",
            "applicable_state": "All India", "eligibility": ["x"]}
    base.update(over)
    return normalize_record(base)


def status(rec, profile):
    return evaluate(rec, normalize_profile(profile)[0])["status"]


def part_a() -> None:
    verified = dict(rules_complete=True, last_verified="2026-01-01", status="active")
    assert status(fake(max_age=25, **verified), {"age": 30}) == "ineligible"
    assert status(fake(max_age=25, **verified), {}) == "insufficient_information"
    assert status(fake(max_age=25, social_categories=["SC"], income_limit_annual=250000, **verified),
                  {"age": 20, "category": "SC", "annual_income": 150000}) == "eligible"
    assert status(fake(max_age=25, social_categories=["SC"], income_limit_annual=250000),
                  {"age": 20, "category": "SC", "annual_income": 150000}) == "potentially_eligible"
    assert status(fake(social_categories=["SC"], income_limit_annual=250000, **verified),
                  {"category": "SC"}) == "insufficient_information"
    assert status(fake(level="State", applicable_state="Karnataka", **verified), {"state": "Bihar"}) == "ineligible"
    assert status(fake(min_education="12th pass", **verified), {"education": "Below 10th"}) == "ineligible"
    assert status(fake(status="closed"), {"age": 20}) == "ineligible"
    # new conditions
    assert status(fake(area="Rural", **verified), {"residence": "Urban"}) == "ineligible"
    assert status(fake(area="Rural", **verified), {"residence": "Rural"}) == "eligible"
    assert status(fake(area="Rural", **verified), {}) == "insufficient_information"
    assert status(fake(bpl_required=True, **verified), {"bpl": "No"}) == "ineligible"
    assert status(fake(bpl_required=True, **verified), {"bpl": "Prefer not to say"}) == "insufficient_information"
    assert status(fake(ex_serviceman_required=True, **verified), {"ex_serviceman": "Yes"}) == "eligible"
    # dynamic fields: only kept for the matching occupation
    p, _ = normalize_profile({"occupation": "Student", "land_acres": 5, "land_status": "Own land", "turnover": 1000})
    assert "land_acres" not in p and "turnover" not in p and p["studying"] == "Yes"
    p, _ = normalize_profile({"occupation": "Farmer", "land_acres": 1.5, "land_status": "Own land", "course": "x"})
    assert p["land_owner"] == "Yes" and "course" not in p
    p, w = normalize_profile({"occupation": "Farmer", "land_acres": 0, "land_status": "Own land"})
    assert "land_owner" not in p and w, "own land with 0 acres must not count as ownership"
    p, _ = normalize_profile({"occupation": "Farmer", "land_status": "Tenant / leased"})
    assert "land_owner" not in p, "tenant status must not be guessed as owner/non-owner"
    assert normalize_profile({"occupation": "Farmer", "land_status": "Landless"})[0]["land_owner"] == "No"
    # validation
    assert normalize_profile({"age": 200})[1] and normalize_profile({"annual_income": -5})[1]
    assert "disability" not in normalize_profile({"disability": "Prefer not to say"})[0]
    # idempotent: normalising twice gives the same result
    once, _ = normalize_profile({"occupation": "Farmer", "land_acres": 2, "land_status": "Own land", "age": 40})
    assert normalize_profile(once)[0] == once
    # completion + required
    assert "Age" in missing_required({}) and profile_completion({})["percent"] == 0
    assert "Agriculture" in profile_categories({"occupation": "Farmer"})
    assert "Education" in profile_categories({"studying": "Yes"})
    print("Part A: all logic tests passed")


PROFILES = {
    "Profile 1 - 20y SC engineering student, Karnataka, Rs 1.5 lakh": {
        "age": 20, "gender": "Male", "state": "Karnataka", "category": "SC", "annual_income": 150000,
        "education": "12th pass", "studying": "Yes", "course": "B.E. Engineering", "study_year": "2nd year",
        "institution_type": "Private college", "occupation": "Student"},
    "Profile 2 - 45y farmer, Bihar, Rs 1.8 lakh, owns 1.5 acres": {
        "age": 45, "gender": "Male", "state": "Bihar", "category": "General", "annual_income": 180000,
        "education": "Below 10th", "occupation": "Farmer", "land_acres": 1.5, "land_status": "Own land"},
    "Profile 3 - 30y OBC self-employed woman, Karnataka, Rs 2.5 lakh": {
        "age": 30, "gender": "Female", "state": "Karnataka", "category": "OBC", "annual_income": 250000,
        "education": "Graduate", "occupation": "Self-employed"},
    "Profile 4 - 35y unemployed graduate, Maharashtra, Rs 1 lakh": {
        "age": 35, "gender": "Male", "state": "Maharashtra", "category": "General", "annual_income": 100000,
        "education": "Graduate", "occupation": "Unemployed", "employment_status": "Looking for work"},
}


def part_b() -> None:
    for title, raw in PROFILES.items():
        profile, warnings = normalize_profile(raw)
        cards, evaluated = select_cards(profile)
        print(f"\n=== {title} ===")
        print(f"completion {profile_completion(profile)['percent']}% | warnings: {warnings}")
        print(f"evaluated {evaluated} schemes, showing {len(cards)} relevant")
        for c in cards:
            print(f"  [{c['status']}] {c['scheme_name'][:62]}")
            print(f"      why shown: {', '.join(c['relevance_reasons']) or '-'}")
            for cond in c["conditions"]:
                print(f"      {cond['result']:7} {cond['name']}: {cond['reason'][:80]}")


if __name__ == "__main__":
    part_a()
    part_b()