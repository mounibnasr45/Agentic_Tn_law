"""The reflection reply parser, in isolation.

Pure logic, no LLM, no database — so unlike test_reflection.py's integration tests these
run in CI unconditionally. That matters: the parser is the component standing between a
free-text model reply and a retrieval call, and its failure mode is spending money
searching the corpus for garbage.

The bias under test is asymmetric and deliberate. A missed term costs the enhancement; a
hallucinated term costs a retrieval, an LLM call, and a rewrite of an answer that was
already correct. Every ambiguous case must resolve toward "no terms".
"""
from app.agent.reflection import MAX_TERM_CHARS, _parse_terms


class TestNoTerms:
    def test_the_sentinel_means_no_terms(self):
        assert _parse_terms("RIEN", 2) == []

    def test_the_sentinel_is_case_insensitive_and_whitespace_tolerant(self):
        assert _parse_terms("  rien  \n", 2) == []
        assert _parse_terms("Rien.", 2) == []

    def test_an_empty_reply_means_no_terms(self):
        assert _parse_terms("", 2) == []
        assert _parse_terms("   \n  ", 2) == []

    def test_a_long_essay_is_rejected_rather_than_parsed(self):
        """A model that ignores the format and reasons out loud must not have its prose
        split into search queries."""
        essay = "Après analyse, plusieurs notions mériteraient d'être approfondies. " * 12
        assert _parse_terms(essay, 2) == []

    def test_a_single_overlong_line_is_dropped(self):
        assert _parse_terms("x" * (MAX_TERM_CHARS + 1), 2) == []


class TestTermExtraction:
    def test_one_term_per_line(self):
        assert _parse_terms("premeditation\ndol general", 2) == ["premeditation", "dol general"]

    def test_bullet_decorations_are_stripped(self):
        """Models add list markers despite being told not to."""
        assert _parse_terms("- premeditation\n* recidive", 2) == ["premeditation", "recidive"]

    def test_numbered_decorations_are_stripped(self):
        assert _parse_terms("1. premeditation\n2) recidive", 2) == ["premeditation", "recidive"]

    def test_surrounding_quotes_are_stripped(self):
        assert _parse_terms('"premeditation"', 2) == ["premeditation"]

    def test_blank_lines_are_ignored(self):
        assert _parse_terms("premeditation\n\n\nrecidive", 2) == ["premeditation", "recidive"]

    def test_accented_french_terms_survive_intact(self):
        """The corpus and the prompts are French; mangling accents here would send a
        mis-spelled query into a retriever whose lexical arm is accent-sensitive."""
        assert _parse_terms("préméditation\ncirconstances aggravantes", 2) == [
            "préméditation",
            "circonstances aggravantes",
        ]


class TestBounds:
    def test_the_term_cap_is_enforced(self):
        """reflection_max_terms bounds retrieval fan-out; a model returning six terms must
        not produce six searches."""
        assert _parse_terms("a\nb\nc\nd\ne\nf", 2) == ["a", "b"]

    def test_a_cap_of_zero_yields_nothing(self):
        assert _parse_terms("premeditation", 0) == []

    def test_duplicates_are_removed_case_insensitively(self):
        """Two spellings of one term would otherwise burn two retrievals on one concept."""
        assert _parse_terms("premeditation\nPremeditation\nPREMEDITATION", 2) == [
            "premeditation"
        ]

    def test_the_sentinel_mixed_into_a_list_is_not_treated_as_a_term(self):
        """A model that hedges — one real term plus RIEN — must not send "RIEN" to the
        retriever as though it were legal vocabulary."""
        assert _parse_terms("premeditation\nRIEN", 2) == ["premeditation"]
