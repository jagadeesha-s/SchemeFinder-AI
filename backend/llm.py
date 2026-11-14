
"""Gemini LLM access for SchemeFinder AI."""

from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser

import config
from prompts.prompts import build_prompt


@lru_cache(maxsize=1)
def get_llm() -> ChatGoogleGenerativeAI:
    """Create and cache the Gemini language model."""

    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. "
            "Please check your .env file or Streamlit Secrets."
        )

    return ChatGoogleGenerativeAI(
        model=config.LLM_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0,
        max_output_tokens=config.LLM_MAX_TOKENS,
    )


def invoke_json(system: str, human: str, **variables) -> dict:
    """Run a prompt through Gemini and parse its JSON response."""

    chain = build_prompt(system, human) | get_llm() | JsonOutputParser()

    last_error = None

    for _ in range(2):
        try:
            result = chain.invoke(variables)

            if isinstance(result, dict):
                return result

        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"The AI model did not return a valid answer: {last_error}"
    )
