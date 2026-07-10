"""LLM interface + implementations (rubric §4 LLM row, §6.5 MOCK_MODE).

`LLM` is the swap seam: MockLLM (canned fixture, keyless), AnthropicLLM (real,
forced-JSON), and a future OllamaLLM (free/local) all satisfy it. `get_llm`
returns the right one from config, degrading to Mock when no key is present so
the system is always runnable.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from analysis.prompts import (
    SYSTEM,
    build_analysis_user_prompt,
    build_classify_prompt,
)
from app.config import get_settings
from fixtures import get_fixture

log = logging.getLogger("callsense.llm")


class LLM(ABC):
    @abstractmethod
    def analyse(self, transcript: str, calibration: list[dict] | None = None) -> str:
        """Return raw JSON text conforming to AnalysisResult."""

    @abstractmethod
    def is_sales_call(self, opening_text: str) -> bool: ...


class MockLLM(LLM):
    """Returns the fixture's canned analysis; the quotes match the transcript."""

    def __init__(self, fixture: str | None = None):
        self.fixture = fixture

    def analyse(self, transcript: str, calibration: list[dict] | None = None) -> str:
        analysis = dict(get_fixture(self.fixture)["analysis"])
        analysis.pop("non_sales", None)
        return json.dumps(analysis)

    def is_sales_call(self, opening_text: str) -> bool:
        return not get_fixture(self.fixture)["analysis"].get("non_sales", False)


class AnthropicLLM(LLM):
    def __init__(self, api_key: str, model: str, classifier_model: str, temperature: float):
        self.api_key = api_key
        self.model = model
        self.classifier_model = classifier_model
        self.temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic  # lazy

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def analyse(self, transcript: str, calibration: list[dict] | None = None) -> str:
        client = self._get_client()
        msg = client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=self.temperature,
            system=SYSTEM,
            messages=[
                {"role": "user",
                 "content": build_analysis_user_prompt(transcript, calibration)}
            ],
        )
        return _extract_json(msg.content[0].text)

    def is_sales_call(self, opening_text: str) -> bool:
        client = self._get_client()
        msg = client.messages.create(
            model=self.classifier_model,
            max_tokens=8,
            temperature=0.0,
            messages=[{"role": "user", "content": build_classify_prompt(opening_text)}],
        )
        return "NON_SALES" not in msg.content[0].text.upper()


def _extract_json(text: str) -> str:
    """Strip markdown fences / prose around a JSON object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def get_llm(fixture: str | None = None) -> LLM:
    s = get_settings()
    if s.mock_mode or not s.anthropic_api_key:
        if not s.mock_mode:
            log.warning("no ANTHROPIC_API_KEY; falling back to MockLLM")
        return MockLLM(fixture)
    return AnthropicLLM(
        api_key=s.anthropic_api_key,
        model=s.llm_model,
        classifier_model=s.classifier_model,
        temperature=s.llm_temperature,
    )
