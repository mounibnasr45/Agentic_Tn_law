"""Streamlit frontend — a pure HTTP client.

This file imports NOTHING from app/. It talks to the FastAPI service over HTTP like any
other client would, which is what turns the layering from a claim into a fact: if the
domain leaked into the UI, this file could not compile.

    uvicorn app.main:app --workers 1          # the API
    streamlit run frontend/streamlit_app.py   # this
"""
import os

import httpx
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000/api")
TIMEOUT = httpx.Timeout(30.0, connect=5.0)

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
st.caption("Recherche ancrée dans la Constitution et le Code Pénal tunisiens.")

status = health()

with st.sidebar:
    st.header("⚙️ État du service")

    if status is None:
        st.error("API injoignable.")
        st.code("uvicorn app.main:app --workers 1")
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
                    st.rerun()
                else:
                    st.error(response.json().get("detail", "Échec de l'authentification."))

if "access_token" not in st.session_state:
    st.info("Connectez-vous pour interroger le corpus.")
    st.stop()

if status is None or status["corpus_chunks"] == 0:
    st.warning("Le corpus n'est pas prêt.")
    st.stop()

query = st.text_input(
    "Votre question juridique",
    placeholder="Quelle est la peine pour un vol commis avec arme ?",
)

if query:
    with st.spinner("Recherche dans les textes..."):
        response = api("POST", "/search", params={"query": query, "top_k": 5})

    if response.status_code != 200:
        st.error(response.json().get("detail", "Erreur."))
        st.stop()

    payload = response.json()
    st.caption(f"Mode de recherche : `{payload['retrieval_type']}`")

    for result in payload["results"]:
        article = result["article_number"] or "Préambule"
        with st.expander(f"**{article}** — {result['source']}  ·  score {result['score']:.3f}"):
            st.write(result["excerpt"])
