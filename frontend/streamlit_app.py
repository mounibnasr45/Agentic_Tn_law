"""Streamlit frontend.

Retrieval now lives in Postgres, so this no longer builds or owns an index — it only
checks that the corpus has been ingested (`python -m app.cli ingest`). The
"Réindexer" button is gone: indexing is an operational task, not a thing a random web
visitor triggers on the shared process that everyone else is querying.

In P4 this becomes a pure HTTP client against the FastAPI service and stops importing
app/ entirely.
"""
import asyncio

import streamlit as st

from app.agent import LegalAgentFR
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.runtime import configure_event_loop
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository
from app.infra.db.session import get_sessionmaker
from app.infra.embeddings.sentence_transformer import SentenceTransformerEmbedder

configure_event_loop()
settings = get_settings()
configure_logging(level=settings.log_level, json_logs=settings.log_json)
log = get_logger(__name__)

st.set_page_config(page_title="🇹🇳 Agent Juridique Tunisien", layout="wide")


@st.cache_resource
def get_embedder() -> SentenceTransformerEmbedder:
    # Caching the MODEL is legitimate: it is stateless, read-only, and expensive to
    # load. Caching the AGENT was not — the agent carries conversation memory, and a
    # process-wide cache made that memory shared across every visitor (bug 2).
    return SentenceTransformerEmbedder(settings.embedding_model_name)


def corpus_size() -> int:
    async def _count() -> int:
        async with get_sessionmaker()() as session:
            return await PostgresChunkRepository(session).count()

    try:
        return asyncio.run(_count())
    except Exception:
        log.exception("corpus_count_failed")
        return -1


st.title("🇹🇳 Agent Juridique Tunisien")
st.caption("Assistant IA ancré dans la Constitution et le Code Pénal tunisiens.")

chunks = corpus_size()

with st.sidebar:
    st.header("⚙️ État du système")
    if chunks < 0:
        st.error("Base de données inaccessible.")
        st.code("docker compose up -d db")
    elif chunks == 0:
        st.warning("Corpus non indexé.")
        st.code("python -m app.cli ingest")
    else:
        st.success(f"Corpus indexé : {chunks} extraits")
        st.caption("Recherche hybride (BM25 lexical + dense pgvector) sur PostgreSQL.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# BUG 2 IS STILL HERE, and is now the last thing keeping this frontend honest: the
# agent (and therefore its ConversationBufferWindowMemory) is per-Streamlit-session but
# not per-user, and there is no user. P5 moves memory into Postgres keyed by an
# authenticated user, at which point it becomes structurally impossible to share.
if chunks > 0 and "agent" not in st.session_state:
    st.session_state.agent = LegalAgentFR(embedder=get_embedder())

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

ready = chunks > 0 and "agent" in st.session_state

if query := st.chat_input("Posez votre question juridique...", disabled=not ready):
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"), st.spinner("L'agent consulte les textes..."):
        response = st.session_state.agent.run(query)
        st.markdown(response["answer"])

    st.session_state.messages.append({"role": "assistant", "content": response["answer"]})
