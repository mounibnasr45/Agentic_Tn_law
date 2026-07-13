"""Article-aware chunking for French legal text.

Fixed-size splitting cuts through the middle of articles. That breaks two things:

  1. A citation to "the back half of Article 264 plus the opening of Article 265" is
     not a citation. The article is the atomic unit of law; a chunk that straddles two
     of them cannot be attributed to either.
  2. The evaluation golden set keys on `expected_article`. If chunks don't carry an
     article number, the metric is not merely inaccurate — it is uncomputable.

So: split on article boundaries first, and only fall back to size-based splitting
*within* an article that is genuinely too long, carrying the article number onto every
part. Chunking strategy then becomes an axis in the ablation harness (fixed-size vs
article-aware), which is how we find out whether this reasoning actually holds.

Pure: no langchain, no I/O.
"""
import re

from app.domain.models import Chunk

# "Article 264", "Art. 12", "Article 45 bis". French legal drafting appends bis/ter/
# quater to interpolate articles without renumbering the code, so "45 bis" is a
# DIFFERENT article from "45" and the suffix must be captured.
ARTICLE_PATTERN = re.compile(
    r"^[ \t]*(?:Article|Art\.)[ \t]+(\d+(?:[ \t]*(?:bis|ter|quater|quinquies))?)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Preferred break points inside an over-long article, most structural first.
_SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split text that exceeds max_chars, preferring the most structural break available."""
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        window = remaining[:max_chars]

        cut = -1
        for separator in _SEPARATORS:
            found = window.rfind(separator)
            # Ignore a break in the first quarter: cutting there produces a runt chunk
            # and leaves the bulk of the text to be split again anyway.
            if found > max_chars // 4:
                cut = found + len(separator)
                break

        if cut == -1:
            cut = max_chars  # no natural boundary; hard-cut rather than emit one huge chunk

        parts.append(remaining[:cut].strip())
        remaining = remaining[max(cut - overlap, 0) :]

    if remaining.strip():
        parts.append(remaining.strip())

    return [p for p in parts if p]


def split_by_article(
    text: str,
    source: str,
    max_chars: int,
    overlap: int,
) -> list[Chunk]:
    """Split a legal document on article boundaries.

    Text before the first article (title page, preamble, table of contents) is kept
    with article_number=None rather than discarded — it is still retrievable, it just
    isn't citable as an article.
    """
    if not text.strip():
        return []

    matches = list(ARTICLE_PATTERN.finditer(text))

    # No article markers at all (a preamble-only document, or an unexpected format):
    # degrade to size-based splitting rather than returning one enormous chunk.
    if not matches:
        return [
            Chunk(content=body, source=source, chunk_index=i, article_number=None)
            for i, body in enumerate(_split_long_text(text.strip(), max_chars, overlap))
        ]

    segments: list[tuple[str | None, str]] = []

    preamble = text[: matches[0].start()].strip()
    if preamble:
        segments.append((None, preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.start() : end].strip()
        if body:
            # Normalise "Art.  45  bis" -> "Article 45 bis" so the golden set can match
            # on a stable string regardless of how the PDF happened to be typeset.
            number = re.sub(r"\s+", " ", match.group(1)).strip().lower()
            segments.append((f"Article {number}", body))

    chunks: list[Chunk] = []
    for article_number, body in segments:
        parts = _split_long_text(body, max_chars, overlap)
        multipart = len(parts) > 1

        for part_index, part in enumerate(parts):
            chunks.append(
                Chunk(
                    content=part,
                    source=source,
                    chunk_index=len(chunks),
                    article_number=article_number,
                    part_index=part_index if multipart else None,
                )
            )

    return chunks
