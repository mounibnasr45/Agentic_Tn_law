# src/tools.py
from langchain.tools import Tool, DuckDuckGoSearchRun # This line is fine
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import List, Dict, Any # Keep Dict, Any if used by other tools

from src.retriever import HybridRetriever
from src.llm_interface import get_llm
import config

# --- Schémas d'entrée pour les outils ---
class RechercheDocumentInput(BaseModel):
    query: str = Field(description="La requête de recherche pour trouver des documents ou articles juridiques pertinents.")

class RechercheWebInput(BaseModel):
    query: str = Field(description="La requête de recherche pour un moteur de recherche web.")

# --- Fonctions des Outils ---
def setup_outil_recherche_documentaire(retriever: HybridRetriever) -> Tool:
    def rechercher_documents(query: str) -> str:
        print(f"Outil: Recherche Documentaire. Requête: '{query}'")
        if not retriever or not retriever.is_initialized:
            return "Le récupérateur de documents n'est pas disponible ou non initialisé."
        
        results = retriever.search(query, top_k=config.TOP_K_RETRIEVER)
        if not results:
            return "Aucun document pertinent trouvé pour votre requête."
        
        context_str = "\n\n---\n\n".join([
            f"Source: {res['metadata'].get('source', 'N/A')}, Morceau: {res['metadata'].get('chunk_num', 'N/A')}\nContenu: {res['content'][:1000]}..."
            for res in results
        ])
        return f"Extraits de documents pertinents trouvés:\n{context_str}"

    return Tool(
        name="outil_recherche_documentaire",
        func=rechercher_documents,
        description="Recherche dans les documents juridiques locaux (lois, constitution, codes) des articles ou informations pertinents. À utiliser pour des questions juridiques spécifiques.",
        args_schema=RechercheDocumentInput
    )

def setup_outil_recherche_web() -> Tool:
    # This line will work after `pip install -U duckduckgo-search`
    search = DuckDuckGoSearchRun() 
    return Tool(
        name="outil_recherche_web",
        func=search.run,
        description="Effectue une recherche web en utilisant DuckDuckGo. Utile pour des connaissances générales, des événements actuels, ou des informations non trouvées dans les documents locaux.",
        args_schema=RechercheWebInput
    )

def get_all_tools(retriever: HybridRetriever) -> List[Tool]:
    return [
        setup_outil_recherche_documentaire(retriever),
        setup_outil_recherche_web(),
    ]
