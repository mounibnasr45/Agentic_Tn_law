"""Builds the configured embedder — Gemini by default, or a local ONNX model —
so callers never construct one directly."""
from app.domain.ports import Embedder


def create_embedder(settings) -> Embedder:  # noqa: ANN001 - Settings, avoiding a cycle
    provider = settings.embedding_provider.lower()

    if provider == "gemini":
        from app.infra.embeddings.gemini_embedder import GeminiEmbedder

        return GeminiEmbedder(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    if provider == "onnx":
        # Imported lazily: onnxruntime is an optional dependency and importing it at module
        # load would make the default provider depend on a package it never uses.
        from app.infra.embeddings.onnx_embedder import OnnxEmbedder

        return OnnxEmbedder(settings.embedding_model_name, settings.embedding_onnx_variant)

    raise ValueError(
        f"unknown EMBEDDING_PROVIDER {settings.embedding_provider!r}; expected 'gemini' or 'onnx'"
    )
