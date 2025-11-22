import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# --- Model Names (Free tier models on OpenRouter) ---
AGENT_LLM_MODEL = os.getenv("AGENT_LLM_MODEL", "deepseek/deepseek-chat") # Good for French and reasoning
SUMMARY_LLM_MODEL = os.getenv("SUMMARY_LLM_MODEL", "mistralai/mistral-7b-instruct-v0.2") # Good for summarization

# --- Embedding Model ---
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# --- Paths ---
# Allow overriding paths via environment variables for Docker/Cloud deployment
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "documents")
VECTOR_STORE_DIR = os.getenv("VECTOR_STORE_DIR", "vector_store")
CHROMA_DB_DIR = os.path.join(VECTOR_STORE_DIR, "chroma_db")
FAISS_INDEX_PATH = os.path.join(VECTOR_STORE_DIR, "faiss_index.bin")

# --- Fixed Document Names ---
# These are the only documents the system will process
DEFAULT_DOCUMENT_FILENAMES = ["Constitution_fr.pdf", "penal_code.pdf"]

# --- Retriever Settings ---
CHUNK_SIZE = 700
CHUNK_OVERLAP = 150
TOP_K_RETRIEVER = 20
HYBRID_WEIGHT_BM25 = 0.4

# --- Agent Settings ---
AGENT_MAX_ITERATIONS = 10
AGENT_REQUEST_TIMEOUT = 120

# Ensure directories exist
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)

# Check if default documents exist
for doc_name in DEFAULT_DOCUMENT_FILENAMES:
    doc_path = os.path.join(DOCUMENTS_DIR, doc_name)
    if not os.path.exists(doc_path):
        print(f"AVERTISSEMENT: Le document par défaut {doc_path} est introuvable. Veuillez l'ajouter au dossier '{DOCUMENTS_DIR}'.")