"""Pre-flight check for a FLARE prototype — run this before spending an afternoon on it.

Answers five separate questions, each of which can independently kill the idea:

  1. Does OpenRouter actually return logprobs for `deepseek/deepseek-chat` (the model
     configured in .env), or does the proxy silently drop the field?
     MEASURED RESULT (this run, deepseek/deepseek-chat via OpenRouter): FAIL — the
     field was requested and came back `null`. See check 2 for the one remaining
     untested path this failure leaves open.
  2. Does DeepSeek's OWN native API (api.deepseek.com, a separate platform key from
     platform.deepseek.com/api_keys — NOT the OpenRouter key) return logprobs when
     OpenRouter's proxy layer is bypassed entirely? This isolates whether check 1's
     failure is OpenRouter's doing or DeepSeek's. `deepseek-chat` is deprecated on
     the native API as of this writing — current models are `deepseek-v4-flash` /
     `deepseek-v4-pro`.
  3. Does `langchain_openai.ChatOpenAI` surface them correctly? There is a known,
     version-dependent gotcha (langchain-ai/langchain#17101) where `model_kwargs=
     {"logprobs": True}` is silently ignored and only `.bind(logprobs=True)` works.
     This checks both, empirically, against whatever version is actually installed —
     don't trust the GitHub issue's age, trust this repo's installed version.
  4. Is Gemini a viable fallback, if you have a key? Optional — skipped cleanly if no
     key or no SDK is present. MEASURED RESULT (gemini-2.5-flash, this run): FAIL —
     server explicitly returned "Logprobs is not enabled for models/gemini-2.5-flash".
  5. Is `langchain` (home of `FlareChain`) even available? This project deliberately
     dropped it in P5 (see requirements.txt) when the agent moved off AgentExecutor
     onto LangGraph's native tool-calling. Re-installing it for a prototype is fine in
     a throwaway venv; it must not quietly end up back in requirements.txt. MEASURED
     RESULT (this run): FAIL — `langchain.chains` doesn't exist in the installed
     version at all; LangChain 1.0's restructuring moved/removed it.

Each check also prints WHAT it saw (not just pass/fail), because "logprobs key is
present" and "logprobs key has a believable, usable confidence signal on our actual
legal corpus" are different claims — see the confidence-demo section for the second.

IMPORTANT — check 2 is deliberately non-blocking even if it passes. A working native
DeepSeek key reopens a real architectural cost (a second LLM provider outside the
single OpenRouter gateway this app is built around) and still leaves the entire FLARE
loop (sentence segmentation, thresholding, masking, re-query, bounded regeneration)
unbuilt. A PASS here means "the option exists," not "go build it."

Makes a small number of real, billed API calls (short completions, ~60 tokens each —
cost is negligible, but it is not free and it is not offline).

Usage:
    python scripts/check_flare_prereqs.py
    python scripts/check_flare_prereqs.py --deepseek-key YOUR_NATIVE_KEY
    python scripts/check_flare_prereqs.py --gemini-key YOUR_KEY --gemini-model gemini-2.5-flash
    python scripts/check_flare_prereqs.py --skip-gemini --skip-deepseek-native
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow `from app.core.config import get_settings` regardless of the cwd this is run
# from — this script lives in scripts/, the `app` package lives one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402

DEMO_QUESTION = "Quelle peine pour un homicide volontaire avec premeditation ?"
DEMO_ARTICLE = "Article 201"  # eval/golden_set.json, id=5 — real corpus question, not invented
LOW_CONFIDENCE_THRESHOLD = 0.5  # exp(logprob) below this = "a FLARE trigger would fire here"


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    detail: str
    blocking: bool = True  # if False, a FAIL doesn't sink the overall verdict


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)
        marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[result.status]
        print(f"{marker} {result.name}")
        for line in result.detail.splitlines():
            print(f"       {line}")
        print()

    def blocking_failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == "FAIL" and r.blocking]


def _token_confidences(logprob_content: list) -> list[tuple[str, float]]:
    """[(token, probability), ...] from an OpenAI-style logprobs.content list."""
    out = []
    for entry in logprob_content:
        token = getattr(entry, "token", None) or entry.get("token")
        logprob = getattr(entry, "logprob", None)
        if logprob is None:
            logprob = entry.get("logprob")
        out.append((token, math.exp(logprob)))
    return out


async def check_openrouter_raw(settings) -> tuple[CheckResult, list[tuple[str, float]]]:
    """Layer 1: does OpenRouter/DeepSeek return logprobs at the raw API level at all?

    Uses the `openai` SDK directly (already a transitive dependency of
    langchain-openai — nothing new to install) so a failure here can't be blamed on
    the LangChain wrapper. Doubles as the confidence-signal demo: asks the real
    golden-set premeditation question and reports the lowest-confidence tokens found.
    """
    if not settings.openrouter_api_key:
        return (
            CheckResult(
                "OpenRouter raw logprobs (deepseek/deepseek-chat)",
                "SKIP",
                "OPENROUTER_API_KEY is empty in .env — nothing to test against.",
            ),
            [],
        )

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    try:
        resp = await client.chat.completions.create(
            model=settings.agent_llm_model,
            messages=[{"role": "user", "content": f"En une phrase, en francais: {DEMO_QUESTION}"}],
            max_tokens=60,
            logprobs=True,
            top_logprobs=3,
        )
    except Exception as exc:  # noqa: BLE001 — report, don't crash the whole script
        return (
            CheckResult(
                "OpenRouter raw logprobs (deepseek/deepseek-chat)",
                "FAIL",
                f"API call raised: {exc!r}",
            ),
            [],
        )

    choice = resp.choices[0]
    content = getattr(getattr(choice, "logprobs", None), "content", None)

    if not content:
        return (
            CheckResult(
                "OpenRouter raw logprobs (deepseek/deepseek-chat)",
                "FAIL",
                "Call succeeded but choices[0].logprobs.content is empty/None — the "
                "field was requested but silently dropped somewhere in the route. "
                "Raw response for inspection:\n"
                + json.dumps(resp.model_dump(), ensure_ascii=False, indent=2)[:800],
            ),
            [],
        )

    confidences = _token_confidences(content)
    lowest = sorted(confidences, key=lambda tc: tc[1])[:3]
    lowest_str = ", ".join(f"{tok!r}={prob:.2f}" for tok, prob in lowest)
    below_threshold = [tc for tc in confidences if tc[1] < LOW_CONFIDENCE_THRESHOLD]

    detail = (
        f"Got {len(confidences)} token logprobs for question id=5 (expected {DEMO_ARTICLE}).\n"
        f"Lowest-confidence tokens: {lowest_str}\n"
    )
    if below_threshold:
        detail += (
            f"{len(below_threshold)} token(s) below {LOW_CONFIDENCE_THRESHOLD} — a FLARE "
            "trigger would fire on this answer. Signal looks usable."
        )
    else:
        detail += (
            f"No token fell below {LOW_CONFIDENCE_THRESHOLD} on this one question — plumbing "
            "works, but this single sample doesn't prove the threshold is well-calibrated. "
            "Try a few more questions before trusting a specific cutoff."
        )

    return (
        CheckResult("OpenRouter raw logprobs (deepseek/deepseek-chat)", "PASS", detail),
        confidences,
    )


DEEPSEEK_NATIVE_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_NATIVE_MODEL = "deepseek-v4-flash"  # deepseek-chat is deprecated natively


async def check_deepseek_native(deepseek_key: str | None, deepseek_model: str) -> CheckResult:
    """Layer 2: bypass OpenRouter entirely — is IT the one dropping logprobs?

    Get a key from https://platform.deepseek.com/api_keys — this is a DIFFERENT
    credential from OPENROUTER_API_KEY; DeepSeek's own dashboard, not OpenRouter's.
    Same question, same golden-set prompt as the OpenRouter check, so the two
    results are directly comparable — the only variable that changes is the route.
    """
    if not deepseek_key:
        return CheckResult(
            "DeepSeek native API logprobs (bypasses OpenRouter)",
            "SKIP",
            "No --deepseek-key given and DEEPSEEK_API_KEY not set. Get one from "
            "https://platform.deepseek.com/api_keys — separate from OPENROUTER_API_KEY. "
            "Not required: the OpenRouter path is the one this app actually runs on.",
            blocking=False,
        )

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=deepseek_key, base_url=DEEPSEEK_NATIVE_BASE_URL)
    try:
        resp = await client.chat.completions.create(
            model=deepseek_model,
            messages=[{"role": "user", "content": f"En une phrase, en francais: {DEMO_QUESTION}"}],
            max_tokens=60,
            logprobs=True,
            top_logprobs=3,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "DeepSeek native API logprobs (bypasses OpenRouter)",
            "FAIL",
            f"API call raised: {exc!r}\n"
            f"If this is a 400/model-not-found, {deepseek_model!r} may not be the right "
            "current model name — check https://api-docs.deepseek.com for the current list.",
            blocking=False,
        )

    choice = resp.choices[0]
    content = getattr(getattr(choice, "logprobs", None), "content", None)

    if not content:
        return CheckResult(
            "DeepSeek native API logprobs (bypasses OpenRouter)",
            "FAIL",
            "Call succeeded but choices[0].logprobs.content is empty/None — DeepSeek's "
            "OWN api dropped it too, not just OpenRouter's proxy. This closes the last "
            "remaining path; FLARE isn't buildable on this provider at all right now.\n"
            "One thing worth ruling out first: DeepSeek's docs say logprobs are disabled "
            "in 'thinking' mode — if this model defaulted into thinking mode, that would "
            "also produce this exact symptom. Check the `thinking` request parameter in "
            "https://api-docs.deepseek.com before concluding it's a hard no.\n"
            "Raw response for inspection:\n"
            + json.dumps(resp.model_dump(), ensure_ascii=False, indent=2)[:800],
        )

    confidences = _token_confidences(content)
    lowest = sorted(confidences, key=lambda tc: tc[1])[:3]
    lowest_str = ", ".join(f"{tok!r}={prob:.2f}" for tok, prob in lowest)

    return CheckResult(
        "DeepSeek native API logprobs (bypasses OpenRouter)",
        "PASS",
        f"Got {len(confidences)} token logprobs for {deepseek_model!r}, bypassing OpenRouter.\n"
        f"Lowest-confidence tokens: {lowest_str}\n"
        "Confirms OpenRouter's proxy layer was the one dropping the field, not DeepSeek. "
        "Reminder from the docstring: this still means adding a second LLM provider "
        "outside the app's single OpenRouter gateway, and the FLARE loop itself is still "
        "unbuilt — this result unblocks the option, it doesn't recommend building it yet.",
        blocking=False,
    )


async def check_langchain_openai_binding(settings) -> CheckResult:
    """Layer 2: does the LangChain wrapper you'll actually build with surface it?

    Tests `.bind(logprobs=True)` against `model_kwargs={"logprobs": True}` side by
    side against your installed langchain-openai version, rather than trusting a
    GitHub issue that may or may not still apply.
    """
    if not settings.openrouter_api_key:
        return CheckResult(
            "langchain_openai ChatOpenAI — bind() vs model_kwargs",
            "SKIP",
            "OPENROUTER_API_KEY is empty in .env.",
        )

    from langchain_openai import ChatOpenAI

    common = dict(
        model=settings.agent_llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        max_tokens=30,
    )
    prompt = "En un mot: qu'est-ce que la premeditation ?"

    async def _probe(llm) -> bool:
        msg = await llm.ainvoke(prompt)
        # response_metadata["logprobs"] can be present but None (not just absent) when
        # the provider drops the field — dict.get's default only covers the absent case.
        content = (msg.response_metadata.get("logprobs") or {}).get("content")
        return bool(content)

    try:
        bind_ok = await _probe(ChatOpenAI(**common).bind(logprobs=True, top_logprobs=3))
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "langchain_openai ChatOpenAI — bind() vs model_kwargs",
            "FAIL",
            f".bind(logprobs=True) raised: {exc!r}",
        )

    try:
        kwargs_ok = await _probe(
            ChatOpenAI(**common, model_kwargs={"logprobs": True, "top_logprobs": 3})
        )
    except Exception:  # noqa: BLE001 - the failure mode IS the result we record
        kwargs_ok = False

    if bind_ok:
        detail = (
            "`.bind(logprobs=True, top_logprobs=N)` → response_metadata populated. "
            "Use this form."
        )
        if not kwargs_ok:
            detail += (
                "\n`model_kwargs={'logprobs': True}` did NOT populate it on this installed "
                "version — langchain-ai/langchain#17101 still reproduces here. Confirmed: "
                "use .bind(), not model_kwargs, when you build the real loop."
            )
        return CheckResult("langchain_openai ChatOpenAI — bind() vs model_kwargs", "PASS", detail)

    return CheckResult(
        "langchain_openai ChatOpenAI — bind() vs model_kwargs",
        "FAIL",
        "Neither .bind() nor model_kwargs populated response_metadata['logprobs']. "
        "The raw OpenRouter check above is the one to trust; if that passed, the gap "
        "is in this langchain-openai version specifically — check its changelog.",
    )


async def check_gemini(gemini_key: str | None, gemini_model: str) -> CheckResult:
    """Layer 3 (optional, not part of this project's config): a fallback provider.

    Not wired into app/core/config.py on purpose — this is your personal exploration
    key, not a project setting, so it's read from an explicit CLI flag / env var here
    rather than added to Settings.
    """
    if not gemini_key:
        return CheckResult(
            "Gemini API logprobs (fallback provider)",
            "SKIP",
            "No --gemini-key given and GEMINI_API_KEY not set. Not required for the "
            "DeepSeek/OpenRouter path.",
            blocking=False,
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return CheckResult(
            "Gemini API logprobs (fallback provider)",
            "SKIP",
            "google-genai not installed. `pip install google-genai` to enable this check "
            "— do not add it to requirements.txt, this is exploratory only.",
            blocking=False,
        )

    try:
        client = genai.Client(api_key=gemini_key)
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=gemini_model,
            contents=f"En une phrase, en francais: {DEMO_QUESTION}",
            config=types.GenerateContentConfig(
                response_logprobs=True,
                logprobs=3,
                max_output_tokens=60,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "Gemini API logprobs (fallback provider)",
            "FAIL",
            f"Call raised: {exc!r}\n"
            "google-genai's API surface changes between versions — if this is a "
            "TypeError/AttributeError rather than an auth error, check the current "
            "GenerateContentConfig field names against installed google-genai version.",
            blocking=False,
        )

    logprobs_result = getattr(resp.candidates[0], "logprobs_result", None)
    if not logprobs_result:
        return CheckResult(
            "Gemini API logprobs (fallback provider)",
            "FAIL",
            f"Call succeeded but candidates[0].logprobs_result is empty for model "
            f"{gemini_model!r} — logprobs requested but not returned for this model/surface.",
            blocking=False,
        )

    return CheckResult(
        "Gemini API logprobs (fallback provider)",
        "PASS",
        f"logprobs_result populated for {gemini_model!r}. Viable as a fallback provider.",
        blocking=False,
    )


def check_langchain_flare_availability() -> CheckResult:
    """Layer 4: is FlareChain even importable — and should it be, in this repo?

    requirements.txt documents that `langchain` (not langchain-core, the full
    package) was deliberately dropped in P5 when the agent moved to LangGraph's
    native tool-calling. FlareChain lives in that dropped package. This check does
    NOT install anything — it only reports what's actually present, and warns
    explicitly if it finds `langchain` already installed (fine for a throwaway
    venv, not fine if it quietly made it into requirements.txt).
    """
    if importlib.util.find_spec("langchain") is None:
        return CheckResult(
            "langchain.chains.flare.base.FlareChain availability",
            "SKIP",
            "`langchain` is not installed — consistent with requirements.txt, which "
            "dropped it in P5 specifically because LangGraph's native tool-calling "
            "replaced AgentExecutor's text-ReAct format.\n"
            "For a FlareChain prototype: `pip install langchain` in an ISOLATED/throwaway "
            "venv, not this project's. If it moves the golden-set numbers, hand-roll the "
            "production version instead of adding this dependency back permanently.",
            blocking=False,
        )

    try:
        from langchain.chains.flare.base import FlareChain  # noqa: F401
    except ImportError as exc:
        return CheckResult(
            "langchain.chains.flare.base.FlareChain availability",
            "FAIL",
            f"`langchain` is installed but FlareChain import failed: {exc!r} — it may have "
            "moved or been removed in this installed version.",
            blocking=False,
        )

    return CheckResult(
        "langchain.chains.flare.base.FlareChain availability",
        "PASS",
        "`langchain` is installed and FlareChain imports cleanly. Reminder: this package "
        "was deliberately removed from requirements.txt in P5 — if it's present now, "
        "confirm that's a throwaway venv and not this project's real environment before "
        "you go further.",
        blocking=False,
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gemini-key", default=os.environ.get("GEMINI_API_KEY"))
    parser.add_argument("--gemini-model", default="gemini-2.5-flash")
    parser.add_argument("--skip-gemini", action="store_true")
    parser.add_argument("--deepseek-key", default=os.environ.get("DEEPSEEK_API_KEY"),
                         help="Native key from https://platform.deepseek.com/api_keys — "
                              "NOT the OpenRouter key.")
    parser.add_argument("--deepseek-model", default=DEFAULT_DEEPSEEK_NATIVE_MODEL)
    parser.add_argument("--skip-deepseek-native", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    report = Report()

    print("=" * 70)
    print("FLARE pre-flight check")
    print(
        f"Configured agent model: {settings.agent_llm_model} "
        f"(via {settings.openrouter_base_url})"
    )
    print("Makes a small number of real, billed API calls (~60 tokens each).")
    print("=" * 70)
    print()

    raw_result, _confidences = await check_openrouter_raw(settings)
    report.add(raw_result)

    if not args.skip_deepseek_native:
        report.add(await check_deepseek_native(args.deepseek_key, args.deepseek_model))

    report.add(await check_langchain_openai_binding(settings))

    if not args.skip_gemini:
        report.add(await check_gemini(args.gemini_key, args.gemini_model))

    report.add(check_langchain_flare_availability())

    print("=" * 70)
    blockers = report.blocking_failures()
    if blockers:
        print(f"NOT READY — {len(blockers)} blocking check(s) failed:")
        for b in blockers:
            print(f"  - {b.name}")
        print("\nFix these before spending time on a FLARE prototype.")
        return 1

    print("READY — required checks passed. Optional/fallback checks may show SKIP/FAIL")
    print("above without blocking; read their detail lines before deciding whether they matter.")
    print("\nNext step: prototype with FlareChain (or the raw logprobs loop) against")
    print("eval/golden_set.json and compare hit@k/MRR to eval/baseline.json before")
    print("committing to a production integration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
