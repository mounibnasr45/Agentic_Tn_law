"""Streamlit frontend.

Still coupled to the domain: it constructs the retriever and agent directly. In P4
it becomes a pure HTTP client against the FastAPI service and stops importing
anything under app/ — at which point it proves the layering instead of violating it.
"""
import streamlit as st

from app.agent import LegalAgentFR
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.document_processor import load_specific_documents, split_documents_into_chunks
from app.retriever import HybridRetriever

settings = get_settings()
configure_logging(level=settings.log_level, json_logs=settings.log_json)
log = get_logger(__name__)

st.set_page_config(page_title="🇹🇳 Agent Juridique Tunisien", layout="wide")


@st.cache_resource
def get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever(persist=True)


@st.cache_resource
def get_legal_agent(_retriever: HybridRetriever) -> LegalAgentFR:
    # BUG 2: the leading underscore on `_retriever` excludes it from Streamlit's cache
    # key, so the key is empty and this hands ONE agent — holding ONE memory buffer —
    # to every visitor in the process. Preserved for P1 (no behaviour change). P5
    # deletes the process-global agent entirely by moving memory into Postgres, keyed
    # by an authenticated user.
    return LegalAgentFR(retriever=_retriever)


def display_chat_message(role: str, content: str, sources: str | None = None) -> None:
    with st.chat_message(role):
        st.markdown(content)
        if sources:
            st.caption(f"Sources: {sources}")


if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🇹🇳 Agent Juridique Tunisien")
st.caption(
    "Un assistant IA pour naviguer dans les documents juridiques tunisiens "
    "(Constitution et Code Pénal)."
)

with st.sidebar:
    st.header("⚙️ Gestion des Documents")
    st.markdown(
        f"Documents attendus dans `{settings.documents_dir}` :\n"
        + "\n".join(f"- `{name}`" for name in settings.default_document_filenames)
    )

    if st.button("Initialiser/Réindexer les Documents Juridiques"):
        missing = settings.missing_documents()
        if missing:
            st.error(
                f"Documents manquants dans '{settings.documents_dir}': {', '.join(missing)}."
            )
        else:
            with st.spinner("Traitement de la Constitution et du Code Pénal en cours..."):
                raw_docs = load_specific_documents()
                if raw_docs:
                    chunks = split_documents_into_chunks(raw_docs)
                    get_hybrid_retriever().build_indices(chunks, persist=True)
                    st.success(
                        f"Traité {len(raw_docs)} documents en {len(chunks)} morceaux. "
                        "Le récupérateur est prêt !"
                    )
                    st.session_state.pop("agent", None)
                    st.rerun()
                else:
                    st.error("Aucun texte n'a pu être extrait des documents.")

    st.info(
        "État du Récupérateur : "
        f"{'Initialisé' if get_hybrid_retriever().is_initialized else 'Non Initialisé'}"
    )

with st.spinner("Chargement des modèles d'IA et initialisation du système..."):
    retriever_instance = get_hybrid_retriever()

if retriever_instance.is_initialized:
    if "agent" not in st.session_state:
        st.session_state.agent = get_legal_agent(retriever_instance)
else:
    st.session_state.pop("agent", None)

for message in st.session_state.messages:
    display_chat_message(message["role"], message["content"], message.get("sources"))

chat_disabled = not (retriever_instance.is_initialized and "agent" in st.session_state)

if query := st.chat_input("Posez votre question juridique ici...", disabled=chat_disabled):
    st.session_state.messages.append({"role": "user", "content": query})
    display_chat_message("user", query)

    with st.spinner("L'agent réfléchit..."):
        response = st.session_state.agent.run(query)

    st.session_state.messages.append(
        {"role": "assistant", "content": response["answer"], "sources": response["sources"]}
    )
    display_chat_message("assistant", response["answer"], response["sources"])

elif not retriever_instance.is_initialized:
    st.warning(
        "Le système de recherche documentaire n'est pas prêt. "
        "Veuillez initialiser les documents via la barre latérale."
    )
