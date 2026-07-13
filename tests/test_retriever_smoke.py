"""Import-level smoke test for the retriever.

The scoring maths lives in src/scoring.py and is tested directly. This module
only guards the wiring: that retriever.py still imports and exposes its contract
after changes. It needs the heavy stack (faiss, sentence-transformers, chroma),
so it skips on machines without them and runs for real in CI.
"""
import pytest

pytest.importorskip("faiss")
pytest.importorskip("sentence_transformers")
pytest.importorskip("langchain_community")


def test_retriever_module_imports():
    import src.retriever  # noqa: F401


def test_hybrid_retriever_exposes_its_search_contract():
    from src.retriever import HybridRetriever

    assert hasattr(HybridRetriever, "search")
    assert hasattr(HybridRetriever, "build_indices")


def test_uninitialised_retriever_returns_no_results_instead_of_raising():
    from src.retriever import HybridRetriever

    retriever = HybridRetriever.__new__(HybridRetriever)  # skip model loading
    retriever.is_initialized = False

    assert retriever.search("quelle est la peine pour vol simple ?") == []
