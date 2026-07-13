from app.domain.chunking import split_by_article

PENAL_CODE = """CODE PENAL TUNISIEN
Dispositions preliminaires.

Article 264
Le vol simple est puni d'un emprisonnement de six mois.

Art. 265
Le vol aggrave est puni d'un emprisonnement de dix ans.

Article 265 bis
Le vol commis avec violence est puni de quinze ans.
"""


def chunk(text: str = PENAL_CODE, max_chars: int = 700, overlap: int = 100):
    return split_by_article(text, source="penal_code.pdf", max_chars=max_chars, overlap=overlap)


class TestArticleBoundaries:
    def test_each_article_becomes_its_own_chunk(self):
        articles = [c.article_number for c in chunk() if c.article_number]

        assert articles == ["Article 264", "Article 265", "Article 265 bis"]

    def test_bis_is_a_distinct_article_not_a_duplicate_of_265(self):
        # French drafting interpolates articles with bis/ter rather than renumbering the
        # code. "265 bis" is a different offence from "265"; collapsing them would
        # attribute a fifteen-year sentence to the wrong article.
        numbers = [c.article_number for c in chunk()]

        assert "Article 265" in numbers
        assert "Article 265 bis" in numbers

    def test_the_abbreviated_form_is_normalised(self):
        # The source PDF writes "Art. 265"; the golden set says "Article 265". They must
        # be the same string or expected_article can never match.
        assert "Article 265" in [c.article_number for c in chunk()]

    def test_an_article_body_is_not_split_across_chunks(self):
        theft = next(c for c in chunk() if c.article_number == "Article 264")

        assert "vol simple" in theft.content
        assert "six mois" in theft.content
        assert "vol aggrave" not in theft.content  # no bleed from the next article

    def test_the_preamble_is_kept_but_is_not_citable(self):
        preamble = chunk()[0]

        assert preamble.article_number is None
        assert "CODE PENAL" in preamble.content


class TestOverlongArticles:
    def test_a_long_article_is_split_but_keeps_its_number(self):
        long_text = "Article 999\n" + "Le contrevenant encourt une sanction. " * 60
        chunks = split_by_article(long_text, source="x.pdf", max_chars=300, overlap=50)

        assert len(chunks) > 1
        assert all(c.article_number == "Article 999" for c in chunks)

    def test_the_parts_of_a_split_article_are_numbered(self):
        long_text = "Article 999\n" + "Le contrevenant encourt une sanction. " * 60
        chunks = split_by_article(long_text, source="x.pdf", max_chars=300, overlap=50)

        assert [c.part_index for c in chunks] == list(range(len(chunks)))

    def test_an_article_that_fits_has_no_part_index(self):
        theft = next(c for c in chunk() if c.article_number == "Article 264")

        assert theft.part_index is None

    def test_chunks_respect_the_size_limit(self):
        long_text = "Article 999\n" + "Le contrevenant encourt une sanction. " * 60
        chunks = split_by_article(long_text, source="x.pdf", max_chars=300, overlap=50)

        assert all(len(c.content) <= 300 for c in chunks)


class TestEdgeCases:
    def test_empty_document_produces_no_chunks(self):
        assert split_by_article("", source="x.pdf", max_chars=700, overlap=100) == []
        assert split_by_article("   \n\n ", source="x.pdf", max_chars=700, overlap=100) == []

    def test_a_document_with_no_articles_degrades_to_size_based_splitting(self):
        text = "Un preambule sans aucun article. " * 50
        chunks = split_by_article(text, source="x.pdf", max_chars=300, overlap=50)

        assert len(chunks) > 1
        assert all(c.article_number is None for c in chunks)
        assert all(len(c.content) <= 300 for c in chunks)

    def test_chunk_index_is_contiguous_across_the_document(self):
        chunks = chunk()

        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_source_is_carried_onto_every_chunk(self):
        assert all(c.source == "penal_code.pdf" for c in chunk())
