# app.py
import streamlit as st
import os

import config 
from src.document_processor import load_specific_documents, split_documents_into_chunks
from src.retriever import HybridRetriever
from src.agent import LegalAgentFR # This import now triggers the chain leading to the error

st.set_page_config(page_title="🇹🇳 Agent Juridique Tunisien", layout="wide")

@st.cache_resource
def get_hybrid_retriever() -> HybridRetriever:
    print("Appel de get_hybrid_retriever() (mise en cache ou création)...")
    retriever = HybridRetriever(persist=True)
    return retriever

@st.cache_resource
def get_legal_agent(_retriever: HybridRetriever) -> LegalAgentFR:
    print("Appel de get_legal_agent() (mise en cache ou création)...")
    # The error happens inside LegalAgentFR's __init__ -> get_all_tools -> setup_outil_recherche_web
    return LegalAgentFR(retriever=_retriever) 

def display_chat_message(role: str, content: any, sources: str = None):
    with st.chat_message(role):
        st.markdown(content)
        if sources and sources != "Les sources devraient être incluses dans la réponse de l'agent si applicable.":
            st.caption(f"Sources: {sources}")

if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🇹🇳 Agent Juridique Tunisien")
st.caption("Un assistant IA pour naviguer dans les documents juridiques tunisiens (Constitution et Code Pénal).")

with st.sidebar:
    st.header("⚙️ Gestion des Documents")
    st.markdown(f"""
    Ce système est configuré pour utiliser les documents suivants :
    - `{config.DEFAULT_DOCUMENT_FILENAMES[0]}`
    - `{config.DEFAULT_DOCUMENT_FILENAMES[1]}`

    Assurez-vous qu'ils sont présents dans le dossier `{config.DOCUMENTS_DIR}`.
    """)

    if st.button("Initialiser/Réindexer les Documents Juridiques", key="process_documents_button"):
        missing_docs = []
        for doc_name in config.DEFAULT_DOCUMENT_FILENAMES:
            doc_path = os.path.join(config.DOCUMENTS_DIR, doc_name)
            if not os.path.exists(doc_path):
                missing_docs.append(doc_name)
        
        if missing_docs:
            st.error(f"Documents manquants dans '{config.DOCUMENTS_DIR}': {', '.join(missing_docs)}. Veuillez les ajouter.")
        else:
            with st.spinner("Traitement de la Constitution et du Code Pénal en cours..."):
                raw_docs = load_specific_documents()
                if raw_docs:
                    chunked_docs = split_documents_into_chunks(raw_docs)
                    retriever_instance_for_build = get_hybrid_retriever()
                    retriever_instance_for_build.build_indices(chunked_docs, persist=True)
                    st.success(f"Traité {len(raw_docs)} documents en {len(chunked_docs)} morceaux. Le récupérateur est prêt !")
                    if "agent" in st.session_state:
                        del st.session_state.agent
                        print("Ancien agent supprimé de la session après réindexation.")
                    st.rerun()
                else:
                    st.error(f"Aucun texte n'a pu être extrait des documents. Vérifiez les fichiers dans '{config.DOCUMENTS_DIR}'.")
    
    retriever_for_status_display = get_hybrid_retriever()
    is_retriever_ready_display = retriever_for_status_display.is_initialized
    st.info(f"État du Récupérateur : {'Initialisé' if is_retriever_ready_display else 'Non Initialisé'}")
    if not is_retriever_ready_display:
         st.toast("Le récupérateur de documents n'est pas prêt. Veuillez utiliser le bouton ci-dessus.", icon="ℹ️")

with st.spinner("Chargement des modèles d'IA et initialisation du système..."):
    retriever_instance = get_hybrid_retriever()
    
is_retriever_currently_initialized = retriever_instance.is_initialized

if is_retriever_currently_initialized:
    if "agent" not in st.session_state:
        print("Création d'une nouvelle instance d'agent...")
        st.session_state.agent = get_legal_agent(retriever_instance) # Error occurs here
elif "agent" in st.session_state:
    print("Récupérateur non initialisé, suppression de l'agent de la session...")
    del st.session_state.agent

for message in st.session_state.messages:
    display_chat_message(message["role"], message["content"], message.get("sources"))

chat_input_disabled = not (is_retriever_currently_initialized and "agent" in st.session_state)

if user_query := st.chat_input("Posez votre question juridique ici...", key="user_query_input", disabled=chat_input_disabled):
    st.session_state.messages.append({"role": "user", "content": user_query})
    display_chat_message("user", user_query)

    if "agent" in st.session_state:
        agent_to_run = st.session_state.agent
        with st.spinner("L'agent réfléchit..."):
            response = agent_to_run.run(user_query)
            answer = response["answer"]
            sources_text = response.get("sources", "N/A ou inclus dans la réponse")
        st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources_text})
        display_chat_message("assistant", answer, sources_text)
    else:
        st.error("Erreur : L'agent n'est pas disponible. Veuillez réessayer d'initialiser les documents.")
elif not is_retriever_currently_initialized:
     st.warning("Le système de recherche documentaire n'est pas prêt. Veuillez initialiser les documents via la barre latérale.")