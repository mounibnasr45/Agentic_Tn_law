from langchain.tools import Tool
from langchain_community.tools import DuckDuckGoSearchRun
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.retriever import HybridRetriever

log = get_logger(__name__)


class RechercheDocumentInput(BaseModel):
    query: str = Field(
        description=(
            "La requête de recherche pour trouver des documents ou articles "
            "juridiques pertinents."
        )
    )


class RechercheWebInput(BaseModel):
    query: str = Field(description="La requête de recherche pour un moteur de recherche web.")


def setup_outil_recherche_documentaire(retriever: HybridRetriever) -> Tool:
    def rechercher_documents(query: str) -> str:
        settings = get_settings()

        if not retriever or not retriever.is_initialized:
            return "Le récupérateur de documents n'est pas disponible ou non initialisé."

        results = retriever.search(query, top_k=settings.top_k_retriever)
        if not results:
            return "Aucun document pertinent trouvé pour votre requête."

        # BUG 4: flattening structured results into a string here is what destroys the
        # citations. Scores, chunk ids and article numbers cannot survive this, which
        # is why agent.run() ends up returning a hardcoded placeholder for `sources`.
        # Fixed in P5, when the tool returns list[RetrievedChunk] and the chat service
        # persists them as citation rows.
        excerpts = "\n\n---\n\n".join(
            f"Source: {r['metadata'].get('source', 'N/A')}, "
            f"Morceau: {r['metadata'].get('chunk_num', 'N/A')}\n"
            f"Contenu: {r['content'][:1000]}..."
            for r in results
        )
        return f"Extraits de documents pertinents trouvés:\n{excerpts}"

    return Tool(
        name="outil_recherche_documentaire",
        func=rechercher_documents,
        description=(
            "Recherche dans les documents juridiques locaux (lois, constitution, codes) "
            "des articles ou informations pertinents. À utiliser pour des questions "
            "juridiques spécifiques."
        ),
        args_schema=RechercheDocumentInput,
    )


def setup_outil_recherche_web() -> Tool:
    search = DuckDuckGoSearchRun()
    return Tool(
        name="outil_recherche_web",
        func=search.run,
        description=(
            "Effectue une recherche web en utilisant DuckDuckGo. Utile pour des "
            "connaissances générales, des événements actuels, ou des informations "
            "non trouvées dans les documents locaux."
        ),
        args_schema=RechercheWebInput,
    )


def get_all_tools(retriever: HybridRetriever) -> list[Tool]:
    return [
        setup_outil_recherche_documentaire(retriever),
        setup_outil_recherche_web(),
    ]
