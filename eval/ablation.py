"""Retrieval ablation.

    python -m eval.ablation                 # sweep every arm, print the table
    python -m eval.ablation --gate          # also fail if hit@5 regressed vs baseline
    python -m eval.ablation --write-baseline

Emits markdown to $GITHUB_STEP_SUMMARY, so the table renders on the pull request itself
rather than being buried in a log.

Requires an ingested corpus: `python -m app.cli ingest`.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.runtime import configure_event_loop
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository
from app.infra.db.session import dispose_engine, get_sessionmaker
from app.infra.embeddings.sentence_transformer import SentenceTransformerEmbedder
from eval.harness import Config, load_golden_set, run

log = get_logger(__name__)

BASELINE = Path(__file__).parent / "baseline.json"

# A regression larger than this fails the build. Not zero: the golden set has 56
# questions, so a single question flipping moves hit@5 by 1.8 points. A zero-tolerance
# gate would fail on noise and be switched off within a week, which is worse than no gate.
MAX_REGRESSION = 0.03

# The weight IS the arm. 0.0 is dense-only, 1.0 is lexical-only, and everything between
# is a hybrid — so one axis produces all three of the arms people usually hand-code.
WEIGHT_SWEEP = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]


def configurations() -> list[Config]:
    configs = [
        Config(name=f"weighted w={w:.1f}", weight_bm25=w) for w in WEIGHT_SWEEP
    ]
    configs.append(Config(name="RRF (rank fusion)", fusion="rrf"))
    # Candidate limit controls the truncation bias in align_candidates: a chunk absent
    # from an arm's top-N is scored 0.0 for that arm, which is not the same as a low
    # score. If a wider candidate pool helps, that bias is real and measurable.
    configs.append(Config(name="weighted w=0.4, cand=100", weight_bm25=0.4, candidate_limit=100))
    configs.append(Config(name="weighted w=0.4, cand=20", weight_bm25=0.4, candidate_limit=20))
    return configs


def _arm(config: Config) -> str:
    if config.fusion == "rrf":
        return "rrf"
    if config.weight_bm25 >= 1.0:
        return "lexical only"
    if config.weight_bm25 <= 0.0:
        return "dense only"
    return "hybrid"


def render_table(rows: list[tuple[Config, dict]], model: str, corpus: int) -> str:
    best = max(rows, key=lambda r: r[1]["hit@5"])

    lines = [
        "## Retrieval ablation",
        "",
        f"`{model}` · {corpus} chunks · {rows[0][1]['n']} golden questions · "
        "article-level relevance",
        "",
        "| configuration | arm | hit@1 | hit@3 | hit@5 | hit@10 | MRR | nDCG@10 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for config, metrics in rows:
        marker = " **←**" if config is best[0] else ""
        lines.append(
            f"| `{config.name}`{marker} | {_arm(config)} | "
            f"{metrics['hit@1']:.3f} | {metrics['hit@3']:.3f} | {metrics['hit@5']:.3f} | "
            f"{metrics['hit@10']:.3f} | {metrics['MRR']:.3f} | {metrics['nDCG@10']:.3f} |"
        )

    lines += [
        "",
        f"**Best hit@5: `{best[0].name}` at {best[1]['hit@5']:.3f}.**",
        "",
        "Metrics are pure arithmetic — no LLM judge. Retrieval is a ranking problem, and "
        "an LLM grader would be nondeterministic, cost money per run, and be unable to "
        "gate a build.",
    ]
    return "\n".join(lines)


async def main_async(args) -> int:
    settings = get_settings()
    questions = load_golden_set()

    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)

    async with get_sessionmaker()() as session:
        repository = PostgresChunkRepository(session)

        corpus = await repository.count()
        if corpus == 0:
            log.error("corpus_empty", remedy="python -m app.cli ingest")
            return 1

        rows = []
        for config in configurations():
            metrics, detail = await run(config, embedder, repository, questions)
            rows.append((config, metrics.as_row() | {"n": metrics.n}))
            log.info("arm_scored", arm=config.name, **metrics.as_row())

            if args.detail and config.name == args.detail:
                for d in detail:
                    if d["found_at_rank"] is None or d["found_at_rank"] > 5:
                        print(f"  MISS  q{d['id']:>2}  expected {d['expected']:<34} "
                              f"got {d['top_3']}")

    table = render_table(rows, settings.embedding_model_name, corpus)
    print("\n" + table + "\n")

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(table + "\n")

    scores = {config.name: metrics for config, metrics in rows}

    if args.write_baseline:
        BASELINE.write_text(
            json.dumps(
                {"model": settings.embedding_model_name, "corpus_chunks": corpus,
                 "scores": scores},
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info("baseline_written", path=str(BASELINE))
        return 0

    if args.gate:
        return _gate(scores)

    return 0


def _gate(scores: dict) -> int:
    if not BASELINE.exists():
        log.warning("no_baseline", remedy="python -m eval.ablation --write-baseline")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["scores"]
    regressions = []

    for name, metrics in scores.items():
        if name not in baseline:
            continue
        delta = metrics["hit@5"] - baseline[name]["hit@5"]
        if delta < -MAX_REGRESSION:
            regressions.append(
                f"{name}: hit@5 {baseline[name]['hit@5']:.3f} -> {metrics['hit@5']:.3f} "
                f"({delta:+.3f})"
            )

    if regressions:
        print("\nRETRIEVAL REGRESSION — build failed:")
        for r in regressions:
            print(f"  {r}")
        return 1

    print(f"\nNo arm regressed by more than {MAX_REGRESSION:.0%} on hit@5.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval.ablation")
    parser.add_argument("--gate", action="store_true", help="fail on regression vs baseline")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--detail", metavar="ARM", help="print misses for one arm")
    args = parser.parse_args()

    configure_event_loop()
    configure_logging(level="WARNING", json_logs=False)

    async def _run() -> int:
        try:
            return await main_async(args)
        finally:
            await dispose_engine()

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
