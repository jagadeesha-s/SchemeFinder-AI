"""Coordinates the five agents.

Speed design
  * Browsing a category (no text typed)  -> 0 LLM calls, 0 embeddings (rule engine over the catalog)
  * Free-text question                   -> Router (1 call) + Retrieval (local)
                                            + Eligibility LLM only if PDF/TXT sources were retrieved
                                            + Explainer (1 call, can be switched off in .env)
  * Repeated identical questions are answered from a small in-memory cache."""
import json
from collections import OrderedDict

import config
import db_config
from agents.application_agent import ApplicationAgent
from agents.eligibility_agent import EligibilityAgent
from agents.explainer_agent import ExplainerAgent
from agents.retrieval_agent import RetrievalAgent
from agents.router_agent import IntentRouterAgent
from backend.catalog import get_by_id, load_catalog, record_text
from backend.rules import (MISSING_QUESTIONS, STATUS_ORDER, build_card, matches_filters)
from backend.utils import clean_profile, missing_fields, norm
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


def _result(intent="discover", message="", cards=None, questions=None, sources=None, profile=None) -> dict:
    return {
        "intent": intent,
        "message": message,
        "cards": cards or [],
        "follow_up_questions": questions or [],
        "sources": sources or [],
        "profile_used": profile or {},
        "disclaimer": config.DISCLAIMER,
    }


def _summary(cards: list[dict]) -> str:
    counts = {}
    for c in cards:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    parts = [f"{counts[s]} {STATUS_WORDS[s]}" for s in STATUS_ORDER if s in counts]
    return (f"I found **{len(cards)}** scheme(s): " + ", ".join(parts) + ". "
            "Statuses come from the rules stored in the database; open **View full details** and confirm "
            "everything on the official portal before applying.")


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
    def _finish(self, intent, cards, profile, questions, message, hide_ineligible, sources=None) -> dict:
        if hide_ineligible:
            cards = [c for c in cards if c["status"] != "ineligible"]
        cards = sorted(cards, key=lambda c: STATUS_ORDER[c["status"]])[: db_config.MAX_BROWSE_RESULTS]
        asks = list(questions)
        for c in cards:
            asks += [MISSING_QUESTIONS[f] for f in c.get("missing_fields", []) if f in MISSING_QUESTIONS]
            asks += c.get("questions_for_user", [])
        asks = list(dict.fromkeys(q for q in asks if q))
        return _result(intent, message or _summary(cards), cards, asks, sources, profile)

    def browse(self, profile: dict, category=None, level=None, hide_ineligible=False, intent="discover") -> dict:
        """Fast path: no LLM, no embeddings."""
        records = [r for r in load_catalog() if matches_filters(r, category, level, profile.get("state"))]
        if not records:
            return _result(intent, "No scheme in the database matches these filters yet. Add verified "
                           "records to data/catalog/ and update the index.", profile=profile)
        cards = [build_card(r, profile) for r in records]
        return self._finish(intent, cards, profile, [], "", hide_ineligible)

    # ------------------------------------------------------------------- main
    def handle(self, query: str, ui_profile: dict | None, mode: str = "auto", category: str | None = None,
               level: str | None = None, hide_ineligible: bool = False) -> dict:
        query = (query or "").strip()
        profile = clean_profile(ui_profile)
        category = category if category in db_config.CATEGORIES else None

        cache_key = json.dumps([query, mode, category, level, hide_ineligible, profile,
                                self.store.version], sort_keys=True, default=str)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]
        result = self._handle(query, profile, mode, category, level, hide_ineligible)
        self._cache[cache_key] = result
        if len(self._cache) > 64:
            self._cache.popitem(last=False)
        return result

    def _handle(self, query, profile, mode, category, level, hide_ineligible) -> dict:
        # ---- fast path: button pressed, nothing typed
        if not query and mode != "auto":
            return self.browse(profile, category, level, hide_ineligible, intent=mode)
        if not query:
            return _result(message="Please describe your situation, pick a category, or fill in your profile first.",
                           questions=[config.FIELD_QUESTIONS[f] for f in missing_fields(profile)], profile=profile)

        # ---- Agent 1: route + extract details from the text
        routed = self.router.run(query)
        profile.update(routed["profile"])
        intent = mode if mode != "auto" else routed["intent"]
        missing = missing_fields(profile)

        # ---- Agent 2: retrieve (metadata-filtered)
        retrieved = self.retriever.run(
            routed["search_query"], profile,
            routed["scheme_name"] if intent == "application" else None, category, level,
        )
        if not retrieved["found"]:
            return _result(
                intent=intent,
                message="I could not find any scheme in the database that matches your request. Try describing "
                "your situation differently or choose another category. Missing schemes may not be added yet.",
                questions=[config.FIELD_QUESTIONS[f] for f in missing], profile=profile)
        sources = retrieved["sources"]

        # ---- general question: Explainer answers directly (needs text sources; catalog text for catalog ids)
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
            return _result(intent, ans["answer"], sources=ans["sources"], profile=profile)

        # ---- Agent 3: eligibility. Catalog schemes -> rule engine (instant). PDFs -> LLM.
        cards = [build_card(rec, profile) for sid in retrieved["catalog_ids"] if (rec := get_by_id(sid))
                 and matches_filters(rec, category, level, None)]
        known_names = {norm(c["scheme_name"]) for c in cards}
        questions = []
        if sources:
            elig = self.eligibility.run(query, profile, missing, retrieved["context"], sources)
            questions += elig["follow_up_questions"]
            for c in elig["schemes"]:
                if norm(c["scheme_name"]) not in known_names:
                    cards.append(c)

        if not cards:
            return _result(intent=intent, message="No matching scheme was found in the database for your request.",
                           questions=questions, profile=profile)

        # ---- Agent 4: application guidance for document-based cards only (catalog cards already have it)
        if intent == "application":
            names = [c["scheme_name"] for c in cards if not c["from_catalog"] and c["status"] != "ineligible"]
            apps = self.application.run(names, profile, retrieved["context"], sources)
            for c in cards:
                found = apps.get(norm(c["scheme_name"]))
                if found:
                    found["official_link"] = found["official_link"] or c.get("official_url")
                    c["application"] = found

        # ---- Agent 5: explain in simple English (one call)
        message = ""
        if db_config.USE_LLM_EXPLAINER:
            exp = self.explainer.explain_results(query, cards)
            message = exp["summary"]
            for c in cards:
                if not c.get("explanation"):
                    c["explanation"] = exp["explanations"].get(norm(c["scheme_name"]), "")

        all_sources = {s["id"]: s for c in cards for s in c["sources"]}
        return self._finish(intent, cards, profile, questions, message, hide_ineligible, list(all_sources.values()))