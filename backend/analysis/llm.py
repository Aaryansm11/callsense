"""LLM interface + implementations (rubric §4 LLM row, §6.5 MOCK_MODE).

`LLM` is the swap seam: MockLLM (canned fixture, keyless), AnthropicLLM (real,
forced-JSON), and a future OllamaLLM (free/local) all satisfy it. `get_llm`
returns the right one from config, degrading to Mock when no key is present so
the system is always runnable.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
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
    def classify(self, opening_text: str) -> dict:
        """Screen the call opening. Returns {"sales": bool, "advisor_is":
        "advisor"|"customer"} — the second field is a content-based check of the
        diariser's role assignment (who is actually the company rep)."""


class MockLLM(LLM):
    """Returns the fixture's canned analysis; the quotes match the transcript."""

    def __init__(self, fixture: str | None = None):
        self.fixture = fixture

    def analyse(self, transcript: str, calibration: list[dict] | None = None) -> str:
        analysis = dict(get_fixture(self.fixture)["analysis"])
        analysis.pop("non_sales", None)
        return json.dumps(analysis)

    def classify(self, opening_text: str) -> dict:
        non_sales = get_fixture(self.fixture)["analysis"].get("non_sales", False)
        return {"sales": not non_sales, "advisor_is": "advisor"}


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

    def classify(self, opening_text: str) -> dict:
        client = self._get_client()
        msg = client.messages.create(
            model=self.classifier_model,
            max_tokens=64,
            temperature=0.0,
            messages=[{"role": "user", "content": build_classify_prompt(opening_text)}],
        )
        return _parse_classify(msg.content[0].text)


# Process-global throttle so the many get_llm() instances a worker creates still
# share one rate limit (protects free-tier quotas).
_throttle_lock = threading.Lock()
_last_call_at = 0.0


def _throttle(min_interval_s: float) -> None:
    global _last_call_at
    if min_interval_s <= 0:
        return
    with _throttle_lock:
        wait = min_interval_s - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


def _is_retryable(exc: Exception) -> bool:
    """Rate limits (429) and transient server errors (503 overload) are retryable."""
    s = str(exc).upper()
    return any(
        token in s
        for token in ("429", "RESOURCE_EXHAUSTED", "QUOTA", "503", "UNAVAILABLE",
                      "OVERLOAD", "HIGH DEMAND")
    )


class GeminiLLM(LLM):
    """Google Gemini (AI Studio key). Native JSON output + client-side rate
    limiting and 429 backoff on top of the pipeline's job-level retries."""

    def __init__(self, api_key, model, classifier_model, temperature,
                 min_interval_s, max_retries):
        self.api_key = api_key
        self.model = model
        self.classifier_model = classifier_model
        self.temperature = temperature
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate(self, model, system, user, json_mode):
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            system_instruction=system,
            response_mime_type="application/json" if json_mode else "text/plain",
            max_output_tokens=2048,
        )
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            _throttle(self.min_interval_s)
            try:
                resp = self._get_client().models.generate_content(
                    model=model, contents=user, config=config
                )
                return resp.text or ""
            except Exception as exc:  # noqa: BLE001
                last = exc
                if _is_retryable(exc) and attempt < self.max_retries:
                    delay = min(30.0, 2 ** attempt) * random.uniform(0.7, 1.3)
                    log.warning("Gemini retryable error; backing off %.1fs (attempt %d): %s",
                                delay, attempt, str(exc)[:120])
                    time.sleep(delay)
                    continue
                raise
        raise last  # type: ignore[misc]

    def analyse(self, transcript: str, calibration: list[dict] | None = None) -> str:
        user = build_analysis_user_prompt(transcript, calibration)
        return _extract_json(self._generate(self.model, SYSTEM, user, json_mode=True))

    def classify(self, opening_text: str) -> dict:
        out = self._generate(
            self.classifier_model, None, build_classify_prompt(opening_text), json_mode=True
        )
        return _parse_classify(out)


def _parse_classify(raw: str) -> dict:
    """Parse the classifier's JSON with safe defaults: an unparseable verdict
    counts as sales (so a real call is never silently unscored) with roles
    trusted as-is."""
    try:
        data = json.loads(_extract_json(raw))
    except (ValueError, TypeError):
        log.warning("classifier returned unparseable verdict: %r", raw[:120])
        return {"sales": True, "advisor_is": "advisor"}
    advisor_is = str(data.get("advisor_is", "advisor")).lower()
    return {
        "sales": bool(data.get("sales", True)),
        "advisor_is": "customer" if advisor_is == "customer" else "advisor",
    }


def _extract_json(text: str) -> str:
    """Strip markdown fences / prose around a JSON object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def get_llm(fixture: str | None = None) -> LLM:
    """Pick the LLM from config. MOCK_MODE always wins (keyless demo). Otherwise
    honour LLM_PROVIDER, then fall back to whatever key is present, then Mock."""
    s = get_settings()
    if s.mock_mode:
        return MockLLM(fixture)

    provider = (s.llm_provider or "").lower()
    if provider == "gemini" and s.gemini_api_key:
        return _gemini(s)
    if provider == "anthropic" and s.anthropic_api_key:
        return _anthropic(s)
    if s.gemini_api_key:
        return _gemini(s)
    if s.anthropic_api_key:
        return _anthropic(s)

    log.warning("MOCK_MODE=false but no LLM key configured; using MockLLM")
    return MockLLM(fixture)


def _gemini(s) -> GeminiLLM:
    return GeminiLLM(
        api_key=s.gemini_api_key,
        model=s.gemini_model,
        classifier_model=s.gemini_classifier_model,
        temperature=s.llm_temperature,
        min_interval_s=s.llm_min_interval_s,
        max_retries=s.llm_max_retries,
    )


def _anthropic(s) -> AnthropicLLM:
    return AnthropicLLM(
        api_key=s.anthropic_api_key,
        model=s.llm_model,
        classifier_model=s.classifier_model,
        temperature=s.llm_temperature,
    )
