import os
import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List

import config

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrait le texte d'un PDF en utilisant PyMuPDF (fitz)"""
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text("text") for page in doc])
        return text
    except Exception as e:
        print(f"Erreur lors de l'extraction du texte du PDF {pdf_path}: {e}")
        return ""

def load_specific_documents() -> List[Document]:
    """Charge les documents par défaut spécifiés dans config.py."""
    docs = []
    print(f"Chargement des documents spécifiés: {config.DEFAULT_DOCUMENT_FILENAMES} depuis le dossier '{config.DOCUMENTS_DIR}'...")
    for filename in config.DEFAULT_DOCUMENT_FILENAMES:
        file_path = os.path.join(config.DOCUMENTS_DIR, filename)
        if not os.path.exists(file_path):
            print(f"AVERTISSEMENT: Document '{filename}' non trouvé dans '{config.DOCUMENTS_DIR}'. Il sera ignoré.")
            continue
        
        if filename.endswith(".pdf"):
            print(f"Traitement du PDF: {filename}")
            text = extract_text_from_pdf(file_path)
            if text:
                docs.append(Document(page_content=text, metadata={"source": filename}))
        # Potentiellement ajouter d'autres types de fichiers si nécessaire à l'avenir
    print(f"Chargé {len(docs)} documents.")
    return docs

def split_documents_into_chunks(
    documents: List[Document],
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP
) -> List[Document]:
    """Divise les documents LangChain en plus petits morceaux."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )
    split_docs = []
    for i, doc in enumerate(documents):
        chunks = text_splitter.split_text(doc.page_content)
        for j, chunk_text in enumerate(chunks):
            split_docs.append(
                Document(
                    page_content=chunk_text,
                    metadata={
                        **doc.metadata,
                        "doc_id": f"doc_{i}",
                        "chunk_num": j + 1,
                        "total_chunks_in_doc": len(chunks)
                    }
                )
            )
    print(f"Divisé {len(documents)} documents en {len(split_docs)} morceaux.")
    return split_docs