# 🇹🇳 Agent Juridique Tunisien

An AI-powered legal assistant designed to answer questions based on Tunisian law (Constitution and Penal Code) using a RAG (Retrieval-Augmented Generation) pipeline and an Agentic workflow.

## 📊 Pipeline & Workflow

The system follows a **Retrieval-Augmented Generation (RAG)** approach combined with a **ReAct (Reason + Act)** agent.

```mermaid
graph TD
    User([User]) -->|Asks Question| UI[Streamlit App]
    UI -->|Passes Query| Agent[Legal Agent (LangChain)]
    
    subgraph "Agentic Workflow (ReAct)"
        Agent -->|Thought: Needs Info?| Decision{Decision}
        Decision -->|Yes: Search Docs| ToolDocs[Tool: Document Search]
        Decision -->|Yes: Search Web| ToolWeb[Tool: Web Search]
        Decision -->|No: Answer| LLM[LLM (DeepSeek)]
    end
    
    subgraph "Retrieval System (Hybrid)"
        ToolDocs -->|Query| Retriever[Hybrid Retriever]
        Retriever -->|Keyword Search| BM25[BM25 Index]
        Retriever -->|Semantic Search| VectorDB[ChromaDB / FAISS]
        BM25 -->|Results| Merger[Merge & Rank]
        VectorDB -->|Results| Merger
    end
    
    subgraph "Data Ingestion"
        PDFs[Legal PDFs] -->|Extract Text| Processor[Document Processor]
        Processor -->|Chunking| Chunks[Text Chunks]
        Chunks --> BM25
        Chunks -->|Embeddings| VectorDB
    end

    Merger -->|Top Context| Agent
    ToolWeb -->|Web Results| Agent
    Agent -->|Final Answer| UI
    UI -->|Display| User
```

## 🚀 Deployment

This project is ready for deployment using Docker.

### Prerequisites

- Docker installed on your machine.
- API Keys for OpenRouter (or OpenAI if configured).

### 1. Build the Docker Image

```bash
docker build -t agentic-tn-law .
```

### 2. Run the Container

You need to pass your API key as an environment variable.

```bash
docker run -p 8501:8501 -e OPENROUTER_API_KEY="your_key_here" agentic-tn-law
```

### 3. Access the App

Open your browser and go to `http://localhost:8501`.

## 📂 Project Structure

- `app.py`: Main Streamlit application.
- `src/`: Source code for the agent, retriever, and tools.
- `documents/`: Folder containing the legal PDF documents.
- `vector_store/`: Persisted embeddings for the search engine.
- `config.py`: Configuration settings.

## 🛠️ Technologies

- **Framework**: LangChain, Streamlit
- **LLM**: DeepSeek (via OpenRouter)
- **Embeddings**: SentenceTransformers (HuggingFace)
- **Vector Store**: ChromaDB
- **Search**: BM25 + Semantic Search (Hybrid)
