"""Embedder selection.

Two implementations satisfy app.domain.ports.Embedder, and which one runs is a deployment
decision rather than a code one — so every entrypoint (app/main.py, app/cli.py,
eval/ablation.py) goes through create_embedder() instead of naming a class. Ingest with
one provider and query with another and every score is meaningless, so the one place that
choice is made had better be shared.

  gemini (default) — no model in the process; ~300MB smaller, which is the only reason
                     this fits a 512MB free tier. Costs a network call per embed.
  onnx             — self-contained local encoder. Better in every way except memory, and
                     memory is the binding constraint. Its dependencies (onnxruntime,
                     tokenizers, huggingface_hub) are deliberately NOT in requirements.txt;
                     install them to use it.
"""
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
