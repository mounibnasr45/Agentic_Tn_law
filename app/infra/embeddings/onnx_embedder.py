"""Torch-free embedder: onnxruntime + tokenizers, no transformers, no torch.

Exists because sentence-transformers hard-depends on torch, and importing torch plus
loading the ~450MB fp32 e5-small weights already exceeds a 512MB Render Free container
before a single request is served (confirmed by a real deploy OOMing at the
"loading_embedder" step, before migrations or ingestion even start). `optimum.onnxruntime`
was considered and ruled out: even `optimum[onnxruntime]` unconditionally depends on
`torch>=1.11` per its own package metadata, so this talks to onnxruntime directly instead.

intfloat/multilingual-e5-small's own HuggingFace repo publishes ONNX exports in its onnx/
subfolder, including an int8-quantized one at 118MB (vs. 470MB fp32) — see _ONNX_VARIANTS.
A parity spike (fp32 ONNX vs. the torch encoder, cosine similarity 1.0000 on real corpus
sentences; int8 vs. torch, 0.994-0.996) confirmed the mean-pooling + normalization below
reproduces sentence-transformers' output before this replaced it.
"""
import asyncio
from collections.abc import Sequence

import numpy as np

from app.core.logging import get_logger

log = get_logger(__name__)

E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "

# Keyed by hand rather than accepting a raw onnx/ filename from settings, so a typo in an
# env var fails at startup with a clear error instead of a confusing 404 from
# huggingface_hub, and so OnnxEmbedder.model_name (below) stays short and readable.
_ONNX_VARIANTS = {
    "int8": "onnx/model_qint8_avx512_vnni.onnx",  # 118MB — default, fits the 512MB tier
    "o4": "onnx/model_O4.onnx",  # 235MB — fallback if int8 ever regresses retrieval eval
    "fp32": "onnx/model.onnx",  # 470MB — diagnostic only, same footprint as torch had
}

# The pre-built fast tokenizer that ships alongside the ONNX exports. See the comment in
# __init__ for why this is loaded directly instead of via transformers.AutoTokenizer.
_TOKENIZER_FILE = "onnx/tokenizer.json"

# e5-small's documented limit. Hardcoded rather than read from tokenizer_config.json:
# reading that file is what pulls transformers back in, and this value is a property of
# the model architecture, not of the deployment.
_MAX_TOKENS = 512


class OnnxEmbedder:
    def __init__(self, model_name: str, onnx_variant: str = "int8") -> None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        if onnx_variant not in _ONNX_VARIANTS:
            raise ValueError(
                f"unknown onnx_variant {onnx_variant!r}; expected one of "
                f"{sorted(_ONNX_VARIANTS)}"
            )

        self._is_e5 = "e5" in model_name.lower()

        onnx_file = _ONNX_VARIANTS[onnx_variant]
        onnx_path = hf_hub_download(repo_id=model_name, filename=onnx_file)

        # `tokenizers` directly, NOT transformers.AutoTokenizer. Measured in a 512MB
        # container: AutoTokenizer.from_pretrained peaked at 449MB RSS because it
        # rebuilds the fast tokenizer from sentencepiece.bpe.model on load, while
        # Tokenizer.from_file on the ALREADY-BUILT tokenizer.json peaked at 342MB — a
        # ~105MB saving that is the difference between fitting the free tier and not.
        # Verified to produce byte-identical input_ids and attention_mask.
        tokenizer_path = hf_hub_download(repo_id=model_name, filename=_TOKENIZER_FILE)
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_truncation(max_length=_MAX_TOKENS)
        # Read the pad token out of the vocabulary rather than hardcoding id 1: it is
        # correct for this XLM-R vocabulary, but a wrong pad id is invisible — it
        # silently embeds a real token where padding was meant, and only shows up as
        # slightly worse retrieval.
        pad_token = "<pad>"
        pad_id = self._tokenizer.token_to_id(pad_token)
        if pad_id is None:
            raise ValueError(f"{model_name} tokenizer has no {pad_token!r} token")
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token, pad_type_id=0)

        # A tiny container has ~1 CPU. onnxruntime defaults to one intra-op thread per
        # visible core, which just adds thread-pool memory/contention here for no
        # throughput gain — the same reasoning app/main.py already applies to uvicorn's
        # WORKERS=1. The CPU memory arena is disabled for the same reason: it trades
        # memory for allocation speed, which is the wrong side of that trade here.
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1
        session_options.inter_op_num_threads = 1
        session_options.enable_cpu_mem_arena = False
        session_options.enable_mem_pattern = False
        self._session = ort.InferenceSession(
            onnx_path, sess_options=session_options, providers=["CPUExecutionProvider"]
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        output_names = [o.name for o in self._session.get_outputs()]
        self._hidden_output_index = (
            output_names.index("last_hidden_state") if "last_hidden_state" in output_names else 0
        )

        # A warm inference at construction: (1) fails fast at startup if the
        # tokenizer/session wiring is wrong, matching the "not ready until it genuinely
        # can serve" philosophy in app/main.py's lifespan; (2) is the cheapest way to
        # learn the output dimensionality.
        probe = self._encode(["query: warmup"])
        self._dimensions = int(probe.shape[1])

        # MUST differ from the plain HF repo id. ingestion_service.needs_processing()
        # compares this against each Chunk.embedding_model to decide whether to re-embed
        # a document (see its docstring). If this collided with the string the old
        # SentenceTransformerEmbedder reported, every existing chunk — embedded by torch,
        # fp32, a different runtime — would be wrongly treated as current even though the
        # vectors differ. The suffix makes that drift-guard force a full, correct
        # re-embed on first run after this swap, with no manual DB truncation needed.
        self._model_name = f"{model_name}::onnx-{onnx_variant}"

        log.info(
            "embedding_model_loaded",
            model=self._model_name,
            onnx_file=onnx_file,
            max_seq_length=_MAX_TOKENS,
            dimensions=self._dimensions,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        # Padding and truncation are configured once on the tokenizer in __init__, so
        # encode_batch already returns equal-length, truncated sequences.
        encodings = self._tokenizer.encode_batch(list(texts))
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

        onnx_inputs = {"input_ids": input_ids, "attention_mask": attention_mask}
        # XLM-R-based tokenizers don't produce token_type_ids (no segment embeddings in
        # the model), but this export still declares it as a required input — feed
        # zeros, matching what a torch forward pass defaults it to when absent.
        if "token_type_ids" in self._input_names:
            onnx_inputs["token_type_ids"] = np.zeros_like(input_ids)
        onnx_inputs = {k: v for k, v in onnx_inputs.items() if k in self._input_names}

        outputs = self._session.run(None, onnx_inputs)
        last_hidden_state = outputs[self._hidden_output_index]  # (batch, seq, hidden)

        # Attention-mask-weighted mean pooling, then L2 normalize — e5's own model-card
        # pooling, and what SentenceTransformer.encode(normalize_embeddings=True) already
        # did for this model before this replaced it.
        mask = attention_mask[..., None].astype(np.float32)
        summed = (last_hidden_state * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = summed / counts

        norms = np.clip(np.linalg.norm(mean_pooled, axis=1, keepdims=True), a_min=1e-12, a_max=None)
        return (mean_pooled / norms).astype(np.float32)

    async def embed_query(self, text: str) -> np.ndarray:
        prefixed = f"{E5_QUERY_PREFIX}{text}" if self._is_e5 else text
        vectors = await asyncio.to_thread(self._encode, [prefixed])
        return vectors[0]

    async def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions))

        prefixed = [f"{E5_PASSAGE_PREFIX}{t}" for t in texts] if self._is_e5 else list(texts)
        return await asyncio.to_thread(self._encode, prefixed)
