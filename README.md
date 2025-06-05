# 🇹🇳 Tunisian Legal AI Assistant

I developed an AI-powered Tunisian Legal Assistant aimed at democratizing access to national legal information. The challenge was the fragmentation and complexity of Tunisian laws, which are often inaccessible to the public. I addressed this by building a Retrieval-Augmented Generation (RAG) system that integrates the Tunisian Constitution, Civil Code, Penal Code, and Labor Code into a unified Chroma vector database, with each article chunked, embedded (using multilingual sentence transformers), and tagged with rich metadata. I implemented a FastAPI backend to handle queries and built an agentic reasoning layer using LangChain’s AgentExecutor and custom tools like lookup_article and compare_articles. The assistant responds to user questions in French or dialectal Arabic with cited legal sources and simple explanations. For the frontend, I created a prototype using Streamlit, and integrated WhatsApp via Twilio for conversational access. The result is a scalable, explainable legal AI assistant that empowers users to navigate Tunisian law more easily, with planned extensions for Arabic support, jurisprudence integration, and fine-tuned LLM deployment.
---

## 🚀 Overview

This project leverages **Agentic RAG (Retrieval-Augmented Generation)** and vector search to provide users with clear, cited answers from four major Tunisian legal texts:

- 🏛️ **Constitution**
- ⚖️ **Civil Code**
- 🔒 **Penal Code**
- 👷 **Labor Code**

The assistant accepts legal questions in **French**, retrieves relevant articles using semantic search, and responds with accurate summaries, citations, and optional legal suggestions.

---

## 🧩 Architecture

### 🔹 Backend
- **Framework**: `FastAPI`
- **Reasoning**: `LangChain` with `AgentExecutor`
- **Vector DB**: `Chroma`
- **Embeddings**: `sentence-transformers` (`MiniLM` multilingual)

### 🔹 Document Processing
- Chunking legal PDFs by article
- Metadata tagging: `code_name`, `article_number`, `language`, `year`
- Semantic indexing with multilingual embeddings

### 🔹 Frontend
- Prototype: `Streamlit` with memory context
- Messaging Bot: (Planned) WhatsApp integration via Twilio

---

## 🛠 Features

- 🔍 **Semantic Search**: Ask legal questions in natural French
- 📚 **Cited Responses**: All answers include article number and legal source
- 🧠 **Agentic Reasoning**: Legal tools like `lookup_article()`, `compare_articles()`
- 🗂 **Metadata Filtering**: Query by law type (e.g. only Labor Code)
- 📖 **Context Memory**: Maintains conversational understanding across turns

---

## 📁 Project Structure

legal_assistant/
├── app/
│ ├── main.py # FastAPI app
│ ├── routes.py # Query endpoints
│ └── utils.py
│
├── ingestion/
│ ├── parse_pdfs.py # Chunk & clean legal texts
│ ├── enrich_metadata.py
│ └── embed_store.py # Embed and store into Chroma
│
├── retrieval/
│ └── vector_search.py
│
├── agents/
│ └── agent_executor.py # LangChain agents and tools
│
├── frontend/
│ └── streamlit_app.py
│
├── chroma_db/ # Persisted vectorstore
├── requirements.txt
└── README.md
