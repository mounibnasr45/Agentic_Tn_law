"""Reflection checkpoint: re-reads a draft answer for legal terms the retrieved
articles never defined, and searches for their definitions before replying."""
import asyncio

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.agent.prompts import FINALIZE_PROMPT, REFLECTION_PROMPT
from app.agent.trace import TraceStep, record
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.models import RetrievedChunk

log = get_logger(__name__)

# The model's "nothing missing" token. Checked case-insensitively against a stripped reply,
# and — importantly — it is not the only path to "no terms": an empty or unparseable reply
# lands in the same place. RIEN is the expected signal, not the required one.
NO_GAPS_SENTINEL = "RIEN"

# A reply longer than this is not a term list. Models under-instructed sometimes return an
# essay explaining their reasoning; parsing that as terms would fire retrieval on garbage.
MAX_REFLECTION_REPLY_CHARS = 500

# A "term" longer than this is a sentence. Same defence, per line.
MAX_TERM_CHARS = 60

# How much of each retrieved chunk to show the reflector. Full articles would blow the
# context budget for a call whose only job is to spot a missing word, and the reflector
# needs enough to recognise a definition, not to reason from it.
CONTEXT_EXCERPT_CHARS = 400


def _parse_terms(reply: str, max_terms: int) -> list[str]:
    """Turn a free-text reflection reply into a bounded list of terms.

    Defensive by construction: every ambiguous case resolves toward "no terms", because a
    false negative costs us the enhancement while a false positive costs a retrieval, an
    LLM call, and a rewrite of a correct answer.
    """
    if not reply:
        return []

    text = reply.strip()

    # Cheap rejections first, before any per-line work.
    if not text or text.upper().startswith(NO_GAPS_SENTINEL):
        return []
    if len(text) > MAX_REFLECTION_REPLY_CHARS:
        log.info("reflection_reply_too_long", length=len(text))
        return []

    terms: list[str] = []
    for raw_line in text.splitlines():
        # Bound checked BEFORE the work, not after appending — otherwise max_terms=0 still
        # lets one term through, and 0 is exactly what someone sets to stop the fan-out.
        if len(terms) >= max_terms:
            break

        # Strip the list decorations models add despite being told not to: "- ", "* ",
        # "1. ", and surrounding quotes.
        line = raw_line.strip().lstrip("-*•").strip()
        while line and line[0].isdigit():
            line = line[1:].lstrip(". )").strip()
        line = line.strip("\"'").strip()

        if not line or len(line) > MAX_TERM_CHARS:
            continue
        # A model that ignored the format and wrote RIEN inside a longer reply still means
        # "nothing missing" — honour the intent rather than the format.
        if line.upper() == NO_GAPS_SENTINEL:
            continue
        # Case-insensitive dedupe, first spelling wins.
        if any(line.casefold() == seen.casefold() for seen in terms):
            continue

        terms.append(line)

    return terms


def _format_context(chunks: list[RetrievedChunk]) -> str:
    """The articles the draft was built from, excerpted.

    The reflector's job is "is this term defined in here?", so it needs the article numbers
    and enough body to recognise a definition — not the full corpus text the drafting agent
    already reasoned over.
    """
    if not chunks:
        return "(aucun extrait)"
    return "\n\n".join(
        f"[{c.article_number or 'préambule'}] {c.content[:CONTEXT_EXCERPT_CHARS]}"
        for c in chunks
    )


async def reflect_and_reground(
    draft: str,
    citations: list[RetrievedChunk],
    llm: BaseChatModel,
    retrieval_tool,
) -> tuple[str, bool]:
    """Return (answer, was_regrounded). Never raises.

    `retrieval_tool` is the SAME tool object the agent used, not a new retriever. That is
    load-bearing, not convenience: the tool appends what it finds to the `retrieved_chunks`
    ContextVar, and chat_service reads that var AFTER this function returns. So a definition
    article pulled in here automatically becomes a Citation row with a real chunk_id foreign
    key — the same durable guarantee the agent's own retrievals get. Constructing a separate
    HybridRetriever here would produce an answer that cites Article 202 with no citation row
    to back it, quietly breaking the one property bug 4's fix was about.
    """
    settings = get_settings()

    # Guard 1: the feature flag. First check, so a disabled feature costs nothing.
    if not settings.reflection_enabled:
        return draft, False

    # Guard 2: nothing to reflect on. A refusal ("je n'ai pas trouvé de disposition") or an
    # empty draft has no terms to ground, and reflecting on one wastes a call to be told so.
    if not draft or not draft.strip() or not citations:
        return draft, False

    try:
        # asyncio.timeout, not the model's own timeout setting: this bounds the WHOLE
        # checkpoint — reflection call, retrievals, and rewrite together. A per-call timeout
        # would let three sequential calls each take the full budget.
        async with asyncio.timeout(settings.reflection_timeout):
            reflection = await llm.ainvoke(
                [
                    HumanMessage(
                        content=REFLECTION_PROMPT.format(
                            max_terms=settings.reflection_max_terms,
                            draft=draft,
                            context=_format_context(citations),
                        )
                    )
                ]
            )

            terms = _parse_terms(
                str(reflection.content or ""), settings.reflection_max_terms
            )

            if not terms:
                log.info("reflection_no_gaps")
                record(
                    TraceStep(
                        kind="reflection",
                        label="Relecture du brouillon",
                        detail="Aucun terme technique non défini — réponse conservée telle quelle.",
                    )
                )
                return draft, False

            log.info("reflection_found_gaps", terms=terms)
            record(
                TraceStep(
                    kind="reflection",
                    label="Relecture du brouillon",
                    detail=(
                        "Terme(s) employé(s) sans définition dans les extraits : "
                        + ", ".join(terms)
                    ),
                )
            )

            # Retrieve a definition per term. Sequential, not asyncio.gather — the tool runs
            # against the request's AsyncSession, and a SQLAlchemy AsyncSession is not safe
            # for concurrent use. domain/retrieval.py documents the exact crash this avoids
            # ("This session is provisioning a new connection"), which fires only on a cold
            # session and therefore passes every warm test. reflection_max_terms is 2; the
            # parallelism was never worth the failure mode.
            definitions: list[str] = []
            for term in terms:
                found = await retrieval_tool.ainvoke(
                    {"query": f"définition de {term} en droit tunisien"}
                )
                if found and found.strip():
                    definitions.append(found)

            # The retrieval found nothing for any term. The corpus genuinely may not define
            # it — a real limit, not a bug. Ship the draft rather than a rewrite that would
            # have to invent the definition it was asked to add.
            if not definitions:
                log.info("reflection_no_definitions_found", terms=terms)
                return draft, False

            final = await llm.ainvoke(
                [
                    HumanMessage(
                        content=FINALIZE_PROMPT.format(
                            draft=draft,
                            definitions="\n\n---\n\n".join(definitions),
                        )
                    )
                ]
            )

            regrounded = str(final.content or "").strip()

            # Last guard. A rewrite that came back empty, or that collapsed to a fraction of
            # the draft, has lost content rather than added it — the failure mode where a
            # model "summarises" instead of rewriting. Half is a deliberately loose floor:
            # we are catching collapse, not policing style.
            if not regrounded or len(regrounded) < len(draft) // 2:
                log.warning(
                    "reflection_rewrite_rejected",
                    draft_length=len(draft),
                    rewrite_length=len(regrounded),
                )
                return draft, False

            log.info("reflection_regrounded", terms=terms, definition_count=len(definitions))
            record(
                TraceStep(
                    kind="answer",
                    label="Réponse réancrée",
                    detail=(
                        f"Définition(s) intégrée(s) pour : {', '.join(terms)}. "
                        "La conclusion juridique du brouillon est conservée."
                    ),
                )
            )
            return regrounded, True

    except TimeoutError:
        # Expected under load and on a cold free-tier dyno. Not exceptional — log at info,
        # not error, so it does not pollute the signal that something is actually broken.
        log.info("reflection_timed_out", timeout=settings.reflection_timeout)
        return draft, False

    except Exception:
        # THE FAIL-OPEN CATCH. Deliberately broad, and deliberately not re-raised.
        #
        # Anything that goes wrong here — an upstream 500, a provider that rejects the
        # prompt, a tool error, a bug in the parser above — must cost the user a gloss, not
        # their answer. chat_service turns exceptions into 502s (bug 3's fix); letting one
        # escape from an optional enhancement would take a correct, already-drafted legal
        # answer and serve it as a server error.
        log.exception("reflection_failed")
        return draft, False
