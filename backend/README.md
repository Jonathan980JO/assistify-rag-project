# Backend Directory

This directory contains all backend server code and AI/ML components for Assistify.

## Core Components

### Main Servers
- **main_llm_server.py** - Main LLM inference server (Qwen2.5-7B)
- **assistify_rag_server.py** - RAG (Retrieval-Augmented Generation) server with TOON optimization
- **login_server.py** - Authentication and session management (moved to Login_system/)

### Database & Storage
- **database.py** - Database models and ORM functions
- **analytics.py** - User analytics and tracking
- **analytics.db.backup** - Analytics database backup

### AI/ML Modules
- **knowledge_base.py** - Knowledge base management for RAG
- **load_documents.py** - Document loading and embedding generation
- **toon.py** - TOON (Token-Oriented Object Notation) encoder/decoder for 40-60% token savings
- **response_validator.py** - LLM response validation and quality checks

### Assets
- **assets/** - Sample files and test data
  - `e2e_test.txt` - End-to-end test data
  - `sample_kb.txt` - Sample knowledge base content

### Vector Database
- **chroma_db/** - ChromaDB vector store for RAG retrieval
  - `chroma.sqlite3` - Vector database

### Models
- **Models/** - Pre-trained AI models
  - `Qwen2.5-7B-LLM/` - Quantized Qwen 2.5 7B language model (GGUF format)
  - `vosk-model-en-us-0.22-lgraph/` - Vosk speech recognition model

### Templates
- **templates/** - Admin panel HTML templates
  - `admin_analytics.html`
  - `admin_errors.html`
  - `admin_users.html`

## Running Backend Services

### Start RAG Server
```powershell
python backend/assistify_rag_server.py
```

### Start LLM Server
```powershell
python backend/main_llm_server.py
```

### Load Knowledge Base
```powershell
python backend/load_documents.py
```

## Key Features

- ✅ RAG with ChromaDB vector search
- ✅ Qwen2.5-7B LLM inference
- ✅ TOON format for 40-60% token savings
- ✅ Speech recognition with Vosk
- ✅ Response validation
- ✅ Analytics tracking

## Dependencies

See `requirements.txt` in project root for all dependencies.
