from langchain_core.documents import Document

from src.document_processor import split_documents_into_chunks


def make_doc(length: int, source: str = "constitution.pdf") -> Document:
    return Document(page_content="a" * length, metadata={"source": source})


def test_empty_input_produces_no_chunks():
    assert split_documents_into_chunks([]) == []


def test_short_document_stays_one_chunk():
    chunks = split_documents_into_chunks([make_doc(100)], chunk_size=700, chunk_overlap=150)

    assert len(chunks) == 1
    assert chunks[0].page_content == "a" * 100


def test_long_document_is_split_and_respects_chunk_size():
    chunks = split_documents_into_chunks([make_doc(5000)], chunk_size=700, chunk_overlap=150)

    assert len(chunks) > 1
    assert all(len(c.page_content) <= 700 for c in chunks)


def test_source_metadata_survives_splitting():
    chunks = split_documents_into_chunks([make_doc(5000, source="penal_code.pdf")])

    assert all(c.metadata["source"] == "penal_code.pdf" for c in chunks)


def test_chunks_are_numbered_sequentially_within_a_document():
    chunks = split_documents_into_chunks([make_doc(5000)], chunk_size=700, chunk_overlap=150)

    assert [c.metadata["chunk_num"] for c in chunks] == list(range(1, len(chunks) + 1))
    assert all(c.metadata["total_chunks_in_doc"] == len(chunks) for c in chunks)


def test_chunks_from_different_documents_get_distinct_doc_ids():
    chunks = split_documents_into_chunks([make_doc(2000), make_doc(2000)])

    assert {c.metadata["doc_id"] for c in chunks} == {"doc_0", "doc_1"}
