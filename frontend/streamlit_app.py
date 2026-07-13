"""Streamlit frontend — a pure HTTP client.

Imports NOTHING from app/. It talks to the FastAPI service over HTTP like any other
client, which makes the layering a fact rather than a claim: if the domain leaked into the
UI, this file could not compile.

    python -m app.run                         # the API
    streamlit run frontend/streamlit_app.py   # this
"""
import os

import httpx
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000/api")
TIMEOUT = httpx.Timeout(120.0, connect=5.0)  # an agent run can take a while

st.set_page_config(page_title="🇹🇳 Agent Juridique Tunisien", layout="wide")


def api(method: str, path: str, **kwargs) -> httpx.Response:
    token = st.session_state.get("access_token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{API}{path}", headers=headers, timeout=TIMEOUT, **kwargs)


def health() -> dict | None:
    try:
        response = api("GET", "/health")
        return response.json() if response.status_code == 200 else None
    except httpx.HTTPError:
        return None


st.title("🇹🇳 Agent Juridique Tunisien")
st.caption("Réponses ancrées dans la Constitution et le Code Pénal, avec citations vérifiables.")

status = health()

with st.sidebar:
    st.header("⚙️ Service")

    if status is None:
        st.error("API injoignable.")
        st.code("python -m app.run")
    else:
        if status["corpus_chunks"] == 0:
            st.warning("Corpus non indexé.")
            st.code("python -m app.cli ingest")
        else:
            st.success(f"{status['corpus_chunks']} extraits indexés")
        st.caption(f"Encodeur : `{status['embedding_model']}`")

    st.divider()

    if "access_token" in st.session_state:
        st.success(f"Connecté : {st.session_state.get('email', '')}")

        # Conversations are per-user and live in Postgres. The old build cached ONE agent
        # object process-wide, so every visitor shared one memory buffer and could read
        # each other's history (bug 2).
        conversations = api("GET", "/conversations")
        if conversations.status_code == 200 and conversations.json():
            st.subheader("Conversations")
            for conversation in conversations.json():
                label = conversation["title"] or "(sans titre)"
                if st.button(label[:40], key=conversation["id"], use_container_width=True):
                    st.session_state.conversation_id = conversation["id"]
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in api("GET", f"/conversations/{conversation['id']}").json()
                    ]
                    st.rerun()

        if st.button("Nouvelle conversation", use_container_width=True):
            st.session_state.pop("conversation_id", None)
            st.session_state.messages = []
            st.rerun()

        if st.button("Se déconnecter"):
            api("POST", "/auth/logout", json={"refresh_token": st.session_state.refresh_token})
            st.session_state.clear()
            st.rerun()
    else:
        st.subheader("Connexion")
        email = st.text_input("Email")
        password = st.text_input("Mot de passe", type="password")

        col_login, col_register = st.columns(2)
        for label, path, column in [
            ("Se connecter", "/auth/login", col_login),
            ("S'inscrire", "/auth/register", col_register),
        ]:
            if column.button(label, use_container_width=True):
                response = api("POST", path, json={"email": email, "password": password})
                if response.status_code in (200, 201):
                    tokens = response.json()
                    st.session_state.access_token = tokens["access_token"]
                    st.session_state.refresh_token = tokens["refresh_token"]
                    st.session_state.email = email
                    st.session_state.messages = []
                    st.rerun()
                else:
                    st.error(response.json().get("detail", "Échec de l'authentification."))

if "access_token" not in st.session_state:
    st.info("Connectez-vous pour interroger le corpus.")
    st.stop()

if status is None or status["corpus_chunks"] == 0:
    st.warning("Le corpus n'est pas prêt.")
    st.stop()

st.session_state.setdefault("messages", [])

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        for citation in message.get("citations", []):
            article = citation["article_number"] or "Préambule"
            with st.expander(f"📖 {article} — {citation['source']}"):
                st.write(citation["excerpt"])

if question := st.chat_input("Posez votre question juridique..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"), st.spinner("L'agent consulte les textes..."):
        response = api(
            "POST",
            "/ask",
            json={
                "question": question,
                "conversation_id": st.session_state.get("conversation_id"),
            },
        )

        if response.status_code != 200:
            # A failure is a failure. The old agent caught every exception and returned the
            # error text AS the assistant's answer, with a 200 OK (bug 3).
            st.error(response.json().get("detail", "Erreur."))
            st.stop()

        payload = response.json()
        st.session_state.conversation_id = payload["conversation_id"]
        st.markdown(payload["answer"])

        # Real citations, each backed by a chunk row in the database. `sources` used to be
        # a hardcoded placeholder string (bug 4).
        for citation in payload["citations"]:
            article = citation["article_number"] or "Préambule"
            with st.expander(f"📖 {article} — {citation['source']}  ·  {citation['score']:.3f}"):
                st.write(citation["excerpt"])

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": payload["answer"],
            "citations": payload["citations"],
        }
    )
