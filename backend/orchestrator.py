"""Coordinates the five agents.

The profile flows through ONE pipeline:
  form -> normalize_profile -> orchestrator -> (rules engine | retrieval -> eligibility) -> cards

Speed design
  * Browsing (no text typed)  -> 0 LLM calls, 0 embeddings (rule engine over the catalog)
  * Free-text question        -> Router (1 call) + local retrieval
                                 + Eligibility LLM only if PDF/TXT sources were retrieved
                                 + Explainer (1 call, can be switched off with USE_LLM_EXPLAINER=false)
  * Identical requests are answered from a small in-memory cache."""
import json
from collections import OrderedDict

import config
import db_config
from agents.application_agent import ApplicationAgent
from agents.eligibility_agent import EligibilityAgent
from agents.explainer_agent import ExplainerAgent
from agents.retrieval_agent import RetrievalAgent
from agents.router_agent import IntentRouterAgent
from backend.catalog import get_by_id, record_text
from backend.profile import normalize_profile
from backend.rules import (MISSING_QUESTIONS, STATUS_ORDER, build_card, matches_filters, select_cards)
from backend.utils import missing_fields, norm
from backend.vector_store import SchemeVectorStore

DEFAULT_QUERIES = {
    "discover": "Find government schemes that match my profile",
    "eligibility": "Check which government schemes I am eligible for",
    "application": "How do I apply for the government schemes that match my profile",
}
STATUS_WORDS = {
    "eligible": "eligible", "potentially_eligible": "possibly eligible",
    "insufficient_information": "need more information", "ineligible": "not eligible",
}


def _counts(cards: list[dict]) -> dict:
    out = {s: 0 for s in STATUS_ORDER}
    for c in cards:
        out[c["status"]] = out.get(c["status"], 0) + 1
    return out


def _result(intent="discover", message="", cards=None, questions=None, sources=None, profile=None,
            evaluated=None, warnings=None) -> dict:
    cards = cards or []
    return {
        "intent": intent,
        "message": message,
        "cards": cards,
        "counts": _counts(cards),
        "evaluated": evaluated if evaluated is not None else len(cards),
        "follow_up_questions": questions or [],
        "sources": sources or [],
        "profile_used": profile or {},
        "profile_warnings": warnings or [],
        "disclaimer": config.DISCLAIMER,
    }


def _summary(cards: list[dict], evaluated: int) -> str:
    counts = _counts(cards)
    parts = [f"{counts[s]} {STATUS_WORDS[s]}" for s in STATUS_ORDER if counts[s]]
    shown = f"Showing **{len(cards)}** of {evaluated} evaluated schemes" if len(cards) != evaluated \
        else f"Evaluated **{evaluated}** scheme(s)"
    return (f"{shown}: " + ", ".join(parts) + ". Statuses come from the conditions stored in the database "
            "(PASS / FAIL / UNKNOWN). Open **View full details** and confirm everything on the official portal.")


class SchemeFinderOrchestrator:
    def __init__(self) -> None:
        self.store = SchemeVectorStore()
        self.router = IntentRouterAgent()
        self.retriever = RetrievalAgent(self.store)
        self.eligibility = EligibilityAgent()
        self.application = ApplicationAgent()
        self.explainer = ExplainerAgent()
        self._cache: OrderedDict = OrderedDict()

    # ---------------------------------------------------------------- helpers
    def _finish(self, intent, cards, profile, questions, message, hide_ineligible, evaluated,
                warnings, sources=None) -> dict:
        if hide_ineligible:
            cards = [c for c in cards if c["status"] != "ineligible"]
        cards = sorted(cards, key=lambda c: (STATUS_ORDER[c["status"]], -c.get("relevance", 0)))
        cards = cards[: db_config.MAX_BROWSE_RESULTS]
        asks = list(questions)
        for c in cards:
            asks += [MISSING_QUESTIONS[f] for f in c.get("missing_fields", []) if f in MISSING_QUESTIONS]
            asks += c.get("questions_for_user", [])
        asks = list(dict.fromkeys(q for q in asks if q))
        return _result(intent, message or _summary(cards, evaluated), cards, asks, sources, profile,
                       evaluated, warnings)

    def browse(self, profile: dict, category=None, level=None, hide_ineligible=False,
               relevant_only=True, intent="discover", warnings=None) -> dict:
        """Fast path: no LLM, no embeddings."""
        cards, evaluated = select_cards(profile, category, level, relevant_only)
        if not cards:
            msg = ("No scheme in the database matches your profile and filters yet. "
                   "Untick 'Show only schemes relevant to my profile' or add verified records to data/catalog/.")
            return _result(intent, msg, profile=profile, evaluated=evaluated, warnings=warnings)
        return self._finish(intent, cards, profile, [], "", hide_ineligible, evaluated, warnings)

    # ------------------------------------------------------------------- main
    def handle(self, query: str, ui_profile: dict | None, mode: str = "auto", category: str | None = None,
               level: str | None = None, hide_ineligible: bool = False, relevant_only: bool = True) -> dict:
        query = (query or "").strip()
        profile, warnings = normalize_profile(ui_profile)
        category = category if category in db_config.CATEGORIES else None

        cache_key = json.dumps([query, mode, category, level, hide_ineligible, relevant_only, profile,
                                self.store.version], sort_keys=True, default=str)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]
        result = self._handle(query, profile, warnings, mode, category, level, hide_ineligible, relevant_only)
        self._cache[cache_key] = result
        if len(self._cache) > 64:
            self._cache.popitem(last=False)
        return result

    def _handle(self, query, profile, warnings, mode, category, level, hide_ineligible, relevant_only) -> dict:
        # ---- fast path: a button was pressed and nothing was typed
        if not query and mode != "auto":
            return self.browse(profile, category, level, hide_ineligible, relevant_only, mode, warnings)
        if not query:
            return _result(message="Please describe your situation, pick a category, or fill in your profile first.",
                           questions=[config.FIELD_QUESTIONS[f] for f in missing_fields(profile)],
                           profile=profile, warnings=warnings)

        # ---- Agent 1: route + extract details from the text (typed details win over the form)
        routed = self.router.run(query)
        typed, typed_warnings = normalize_profile(routed["profile"])
        profile.update(typed)
        profile, _ = normalize_profile(profile)      # drop fields that no longer fit the occupation
        warnings = warnings + typed_warnings
        intent = mode if mode != "auto" else routed["intent"]
        missing = missing_fields(profile)

        # ---- Agent 2: retrieve (metadata-filtered, profile re-ranked, de-duplicated)
        retrieved = self.retriever.run(
            routed["search_query"], profile,
            routed["scheme_name"] if intent == "application" else None, category, level,
        )
        if not retrieved["found"]:
            return _result(
                intent=intent,
                message="I could not find any scheme in the database that matches your request. Try describing "
                "your situation differently or choose another category. The scheme may not be added yet.",
                questions=[config.FIELD_QUESTIONS[f] for f in missing], profile=profile, warnings=warnings)
        sources = retrieved["sources"]

        # ---- general question: Explainer answers directly
        if intent == "general":
            context, srcs = retrieved["context"], dict(sources)
            for sid in retrieved["catalog_ids"][:3]:
                rec = get_by_id(sid)
                if rec:
                    key = f"S{len(srcs) + 1}"
                    srcs[key] = {"id": key, "file": rec.get("_file", "catalog"), "page": 0,
                                 "source_document": rec["source_document"],
                                 "official_url": rec["official_url"] or rec["source_url"] or "",
                                 "last_verified": rec["last_verified"] or ""}
                    context += f"\n\n---\n\n[{key}] {record_text(rec)}"
            ans = self.explainer.answer_general(query, context, srcs)
            return _result(intent, ans["answer"], sources=ans["sources"], profile=profile, warnings=warnings)

        # ---- Agent 3: eligibility. Catalog schemes -> rule engine (instant). PDFs -> LLM conditions.
        cards = []
        for sid in retrieved["catalog_ids"]:
            rec = get_by_id(sid)
            if rec and matches_filters(rec, category, level, None):
                cards.append(build_card(rec, profile))
        known_names = {norm(c["scheme_name"]) for c in cards}
        questions = []
        if sources:
            elig = self.eligibility.run(query, profile, missing, retrieved["context"], sources)
            questions += elig["follow_up_questions"]
            cards += [c for c in elig["schemes"] if norm(c["scheme_name"]) not in known_names]

        if not cards:
            return _result(intent=intent, message="No matching scheme was found in the database for your request.",
                           questions=questions, profile=profile, warnings=warnings)

        # ---- Agent 4: application guidance for document-based cards (catalog cards already have it)
        if intent == "application":
            names = [c["scheme_name"] for c in cards if not c["from_catalog"] and c["status"] != "ineligible"]
            apps = self.application.run(names, profile, retrieved["context"], sources)
            for c in cards:
                found = apps.get(norm(c["scheme_name"]))
                if found:
                    found["official_link"] = found["official_link"] or c.get("official_url")
                    c["application"] = found

        # ---- Agent 5: explain in simple English (one call; AI wording is shown separately from official facts)
        message = ""
        if db_config.USE_LLM_EXPLAINER:
            exp = self.explainer.explain_results(query, cards)
            message = exp["summary"]
            for c in cards:
                if not c.get("explanation"):
                    c["explanation"] = exp["explanations"].get(norm(c["scheme_name"]), "")

        all_sources = {s["id"]: s for c in cards for s in c["sources"]}
        return self._finish(intent, cards, profile, questions, message, hide_ineligible, len(cards),
                            warnings, list(all_sources.values()))