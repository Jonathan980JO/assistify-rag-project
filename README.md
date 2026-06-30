# Assistify v1.0

<p align="center">
  <h3 align="center">AI-Powered Enterprise Help Desk Platform</h3>
  <p align="center">
    Retrieval-Augmented Generation (RAG) • Local LLMs • Voice Assistant • Multi-Tenant Architecture
  </p>
</p>

---

## Overview

Assistify is an enterprise AI help desk platform that transforms organizational knowledge into an intelligent support assistant.

Organizations can upload their own documents, policies, manuals, and knowledge-base content, allowing users to receive accurate, context-aware answers through natural language conversations.

Unlike traditional chatbots, Assistify uses Retrieval-Augmented Generation (RAG) to ground responses in uploaded documents, reducing hallucinations and improving answer reliability.

The platform supports:

- AI-powered support conversations
- Knowledge-base management
- Multi-tenant organizations
- Voice interaction
- Role-based access control
- Analytics and monitoring
- Local AI inference for privacy and cost efficiency

---

## Why Assistify?

Organizations face several challenges with traditional customer support:

- Large amounts of information scattered across PDFs and documents
- Repetitive customer questions
- Slow response times
- High support costs
- Limited support availability
- Inconsistent answers between agents

Assistify addresses these problems by providing a 24/7 AI assistant capable of retrieving information directly from organizational knowledge bases and generating grounded responses.

---

## Key Features

### AI Support Assistant

- Retrieval-Augmented Generation (RAG)
- Context-aware responses
- Tenant-specific knowledge retrieval
- Conversation history
- Streaming responses

### Knowledge Base Management

- PDF document upload
- Automatic document indexing
- Semantic search
- Vector embeddings
- Document re-indexing

### Voice Assistant

- Speech-to-Text
- Text-to-Speech
- English voice support
- Arabic voice support
- Real-time voice conversations

### Multi-Tenant Architecture

- Multiple organizations on one platform
- Complete tenant isolation
- Tenant-specific knowledge bases
- Tenant-specific users and conversations

### Security & Authentication

- Session-based authentication
- OTP verification
- Google OAuth
- Multi-Factor Authentication (MFA)
- Role-Based Access Control (RBAC)
- CSRF protection
- Security event logging

### Analytics & Monitoring

- Usage analytics
- Feedback tracking
- Audit logs
- Knowledge-base monitoring
- Support ticket management

---

## System Architecture

```text
┌─────────────────────┐
│     React UI        │
│     Next.js         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    Login Server     │
│      FastAPI        │
│      Port 7001      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     RAG Server      │
│      FastAPI        │
│      Port 7000      │
└──────┬─────┬────────┘
       │     │
       │     │
       ▼     ▼
 ┌────────┐ ┌─────────┐
 │ChromaDB│ │ Ollama  │
 └────────┘ └─────────┘
       │
       ▼
 ┌─────────┐
 │ Piper   │
 │   TTS   │
 └─────────┘
```

---

## Technology Stack

### Frontend

- React
- Next.js
- TypeScript
- Tailwind CSS

### Backend

- Python
- FastAPI
- WebSockets

### AI & RAG

- Ollama
- Qwen Models
- ChromaDB
- Sentence Transformers
- Cross Encoder Reranking

### Voice

- Faster Whisper
- Piper TTS

### Database

- SQLite

### Authentication

- Session Cookies
- Google OAuth
- OTP Verification
- MFA

---

## User Roles

### SuperAdmin

Platform-wide administration.

Capabilities:

- Create tenants
- Manage organizations
- Create Master Admins
- Monitor platform usage

### Master Admin

Organization owner.

Capabilities:

- Manage tenant administrators
- Manage tenant resources
- View analytics
- Manage users

### Admin

Organization administrator.

Capabilities:

- Manage employees
- Manage customers
- Manage knowledge base
- Review support tickets

### Employee

Support staff.

Capabilities:

- Assist customers
- Access organizational knowledge
- Manage assigned tickets

### Customer

End users.

Capabilities:

- Chat with AI assistant
- Use voice assistant
- Access organization knowledge
- Submit support requests

---

## RAG Pipeline

Assistify uses a Retrieval-Augmented Generation workflow:

### 1. Upload

Administrator uploads PDF documents.

### 2. Processing

Documents are:

- Extracted
- Cleaned
- Chunked
- Embedded

### 3. Storage

Embeddings are stored in ChromaDB.

### 4. Retrieval

Relevant document chunks are retrieved using semantic search.

### 5. Reranking

Retrieved results are reranked for relevance.

### 6. Generation

The LLM generates a response grounded in retrieved content.

### 7. Validation

Responses pass through validation before being delivered to the user.

---

## Voice Pipeline

```text
User Speech
      │
      ▼
Speech-To-Text
(Faster Whisper)
      │
      ▼
RAG Retrieval
      │
      ▼
LLM Generation
      │
      ▼
Text-To-Speech
(Piper)
      │
      ▼
Audio Response
```

---

## Repository Structure

```text
Assistify-v1.0
│
├── assistify-ui-design/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   └── out/
│
├── backend/
│   ├── routers/
│   ├── services/
│   ├── repositories/
│   ├── voice_audio/
│   └── assets/
│
├── Login_system/
│
├── tts_service/
│
├── xtts_service/
│
├── docs/
│
├── tests/
│
├── scripts/
│
├── environment_main.yml
│
└── start_main_servers.py
```

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/Jonathan980JO/assistify-rag-project.git

cd assistify-rag-project
```

### 2. Create Environment

```bash
conda env create -f environment_main.yml
```

### 3. Activate Environment

```bash
conda activate assistify_main
```

### 4. Create Configuration File

```bash
copy .env.example .env
```

Configure values as needed.

### 5. Initialize Database

```bash
python Login_system/init_users_db.py
```

### 6. Start System

```bash
python start_main_servers.py
```

---

## First Login

Default bootstrap account:

```text
Username: superadmin
Password: superadmin
```

After login:

1. Create tenants
2. Create Master Admins
3. Assign administrators
4. Upload knowledge-base documents
5. Start using the platform

---

## Screenshots

Add screenshots here:

### Dashboard

![Dashboard](docs/screenshots/dashboard.png)

### Chat Interface

![Chat](docs/screenshots/chat.png)

### Knowledge Base

![Knowledge Base](docs/screenshots/knowledge-base.png)

### Analytics

![Analytics](docs/screenshots/analytics.png)

---

## Project Highlights

- Enterprise AI Help Desk Platform
- Retrieval-Augmented Generation (RAG)
- Local LLM Inference
- Multi-Tenant SaaS Architecture
- Voice Assistant Support
- Tenant-Isolated Knowledge Bases
- Role-Based Access Control
- Real-Time Chat & Voice
- Analytics & Monitoring
- Secure Authentication System

---

## Future Improvements

Potential future enhancements:

- Human-agent escalation
- Mobile applications
- CRM integrations
- Advanced analytics
- Additional language support
- Cloud deployment options
- Enterprise integrations

---

## Academic Project

This project was developed as a Bachelor of Science Graduation Project at the Arab Academy for Science, Technology & Maritime Transport (AAST). :contentReference[oaicite:0]{index=0}

### Team

- Ahmed Khaled
- Ahmed Ayman
- Ahmed Fateh
- Yassin Adel
- Jonathan Samy

### Supervisor

- Dr. Ahmed Salem

---

## License

This repository is provided for educational, research, and portfolio purposes.

---

## Assistify v1.0

Transforming organizational knowledge into intelligent support.
