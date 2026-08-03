"""Test script: does ANY current Gemini model actually return logprobs, and if one
does, does a minimal FLARE loop (confidence-trigger -> retrieve -> regenerate) work?

WHY THIS EXISTS: a claim came in (from an unstated source, styled like an LLM answer
rather than a live test) asserting gemini-2.5-pro, 2.5-flash, 2.5-flash-lite, and
2.0-flash all support logprobs via generateContent. That directly contradicts a REAL
call already made in this project: gemini-2.5-flash returned "Logprobs is not enabled
for models/gemini-2.5-flash" — a live 400 from Google's own server, not a stale doc.
Independent forum/GitHub reports found separately also contradict the "2.5 Pro: yes"
claim specifically. Rather than trust either side, this tests every model in that
claim, directly, and reports what actually comes back.

Two parts:
  1. check_model_logprobs() — one short real call per model, reports whether
     candidates[0].logprobs_result is actually populated. This is the part that
     settles the disagreement.
  2. run_flare_demo() — only runs against the first model that passes part 1. Shows
     the real mechanism end to end: generate an answer, find a low-confidence token,
     formulate a retrieval query for it, and regenerate the sentence with retrieved
     context spliced in.

WHAT'S REAL AND WHAT'S A STUB: every logprobs check and every generation call is a
real, billed API call. The RETRIEVAL step in the demo is a labeled mock — it does not
call this project's actual HybridRetriever/pgvector-backed corpus, because that needs
a running Postgres + embedding model, which is out of scope for a standalone script
that should run in seconds with just an API key. `mock_retrieve()` is the one function
you'd swap for a real `HybridRetriever.search()` call in production; everything around
it is the actual FLARE control flow.

Usage:
    python scripts/test_flare_gemini.py --gemini-key AIzaSy...
    python scripts/test_flare_gemini.py --gemini-key AIzaSy... --models gemini-2.5-pro
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import re

DEMO_QUESTION = "Quelle peine pour un homicide volontaire avec premeditation ?"
DEMO_ARTICLE = "Article 201"  # eval/golden_set.json, id=5 — same real question used throughout

# Exactly the four models named in the disputed claim — test the actual claim, not a
# different set that would be easier to defend either way.
DEFAULT_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

LOW_CONFIDENCE_THRESHOLD = 0.5


def _gemini_token_confidences(logprobs_result) -> list[tuple[str, float]]:
    """[(token, probability), ...] from a google-genai LogprobsResult.

    Defensive about attribute naming — the google-genai SDK has changed field names
    across versions (this whole investigation has been full of exactly that kind of
    surprise), so this tries the documented snake_case names and falls back to
    reporting nothing rather than crashing if the shape differs.
    """
    chosen = getattr(logprobs_result, "chosen_candidates", None)
    if chosen is None:
        chosen = getattr(logprobs_result, "chosenCandidates", None) or []

    out = []
    for cand in chosen:
        token = getattr(cand, "token", None)
        logprob = getattr(cand, "log_probability", None)
        if logprob is None:
            logprob = getattr(cand, "logprobability", None)
        if token is None or logprob is None:
            continue
        out.append((token, math.exp(logprob)))
    return out


async def check_model_logprobs(client, genai_types, model: str) -> tuple[bool, str]:
    """One real call per model. Returns (supported, detail)."""
    try:
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=f"En une phrase, en francais: {DEMO_QUESTION}",
            config=genai_types.GenerateContentConfig(
                response_logprobs=True,
                logprobs=5,
                max_output_tokens=60,
                temperature=0,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — report every model, don't abort the sweep
        return False, f"Call raised: {exc!r}"

    logprobs_result = getattr(resp.candidates[0], "logprobs_result", None)
    if not logprobs_result:
        return False, "Call succeeded but candidates[0].logprobs_result is empty."

    confidences = _gemini_token_confidences(logprobs_result)
    if not confidences:
        return False, (
            f"logprobs_result is present but token extraction found nothing — raw: "
            f"{logprobs_result!r}"[:400]
        )

    lowest = sorted(confidences, key=lambda tc: tc[1])[:3]
    lowest_str = ", ".join(f"{tok!r}={prob:.2f}" for tok, prob in lowest)
    return True, f"{len(confidences)} token logprobs returned. Lowest-confidence: {lowest_str}"


def mock_retrieve(query: str) -> str:
    """STUB — not this project's real corpus. Swap for HybridRetriever.search(query, top_k=3)
    in production; everything calling this function is the real FLARE control flow.
    """
    return (
        "[MOCK RETRIEVAL — not the real corpus] Article 202 (exemple) : La préméditation "
        "consiste dans le dessein formé avant l'action de commettre un crime ou un délit "
        "déterminé."
    )


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


async def run_flare_demo(client, genai_types, model: str) -> None:
    print(f"\n--- FLARE demo on {model} ---")

    resp = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=(
            f"Réponds en francais, en 2-3 phrases: {DEMO_QUESTION} "
            "Utilise le terme juridique précis si pertinent."
        ),
        config=genai_types.GenerateContentConfig(
            response_logprobs=True,
            logprobs=5,
            max_output_tokens=120,
            temperature=0,
        ),
    )

    full_text = resp.candidates[0].content.parts[0].text
    logprobs_result = getattr(resp.candidates[0], "logprobs_result", None)
    confidences = _gemini_token_confidences(logprobs_result) if logprobs_result else []

    print(f"Generated (expected grounding: {DEMO_ARTICLE}):\n  {full_text!r}")

    if not confidences:
        print("No usable per-token confidence data — can't demonstrate the trigger on this call.")
        return

    below = [(tok, prob) for tok, prob in confidences if prob < LOW_CONFIDENCE_THRESHOLD]
    if not below:
        print(
            f"No token fell below {LOW_CONFIDENCE_THRESHOLD} on this generation — "
            "plumbing works, but nothing to trigger on for this particular answer."
        )
        return

    trigger_token, trigger_prob = below[0]
    print(f"\nTRIGGER: token {trigger_token!r} at confidence {trigger_prob:.2f} "
          f"(below {LOW_CONFIDENCE_THRESHOLD})")

    sentences = _split_sentences(full_text)
    target_sentence = next((s for s in sentences if trigger_token.strip() in s), sentences[-1])
    print(f"Enclosing sentence: {target_sentence!r}")

    query = f"définition juridique de {trigger_token.strip()} en droit tunisien"
    print(f"Formulated retrieval query: {query!r}")

    retrieved = mock_retrieve(query)
    print(f"Retrieved context: {retrieved!r}")

    regen = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=(
            f"Reformule cette phrase en integrant precisement ce contexte juridique, "
            f"sans changer le sens: \n\nPhrase: {target_sentence}\n\n"
            f"Contexte a integrer: {retrieved}"
        ),
        config=genai_types.GenerateContentConfig(max_output_tokens=120, temperature=0),
    )
    regenerated = regen.candidates[0].content.parts[0].text
    print(f"\nBEFORE (ungrounded):  {target_sentence!r}")
    print(f"AFTER  (regrounded):  {regenerated!r}")
    print(
        "\n(Retrieval above is the mock — swap mock_retrieve() for this project's real "
        "HybridRetriever.search() to make this a production FLARE step.)"
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gemini-key", default=os.environ.get("GEMINI_API_KEY"))
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS),
                         help="Comma-separated model list to test.")
    args = parser.parse_args()

    if not args.gemini_key:
        print("No --gemini-key given and GEMINI_API_KEY not set. Nothing to test.")
        return 1

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("google-genai not installed. `pip install google-genai` to run this script.")
        return 1

    client = genai.Client(api_key=args.gemini_key)
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    print("=" * 70)
    print("Gemini logprobs sweep — settling the model-support disagreement with real calls")
    print("=" * 70)

    results: dict[str, bool] = {}
    for model in models:
        supported, detail = await check_model_logprobs(client, types, model)
        results[model] = supported
        marker = "[PASS]" if supported else "[FAIL]"
        print(f"{marker} {model}")
        print(f"       {detail}")
        print()

    print("=" * 70)
    print("Summary vs. the disputed claim:")
    for model in models:
        verdict = "supports logprobs" if results[model] else "does NOT support logprobs"
        print(f"  {model}: {verdict}")
    print("=" * 70)

    first_working = next((m for m, ok in results.items() if ok), None)
    if first_working:
        await run_flare_demo(client, types, first_working)
        return 0

    print("\nNo model in this list returned usable logprobs. The disputed claim does not "
          "hold for any of these models against this project's actual key and account.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
