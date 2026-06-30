# Assistify - AI-Powered Voice Help Desk System
## Complete Project Briefing & Technical Documentation

---

## 1. SYSTEM OVERVIEW

### Project Purpose
Assistify is an enterprise-grade AI-powered help desk system that provides real-time voice and text-based customer support using advanced Retrieval-Augmented Generation (RAG) technology. The system combines automatic speech recognition, large language model inference, and knowledge base retrieval to deliver accurate, context-aware responses to user queries.

### Core Capabilities
- **Voice-to-Voice Interaction**: Users speak questions, receive spoken AI responses
- **Real-time ASR**: Automatic Speech Recognition using faster-whisper (CPU)
- **GPU-Accelerated LLM**: Qwen2.5:3b via Ollama on NVIDIA GPU
- **RAG System**: Context retrieval from knowledge base documents
- **Multi-user Authentication**: Role-based access control (Admin/Employee/Customer)
- **Admin Dashboard**: Complete management interface for users, analytics, and knowledge base
- **Analytics Tracking**: Usage statistics, error monitoring, and system health metrics

### Target Users
1. **Customers**: End users seeking support via voice/text chat
2. **Employees**: Support staff with chat access + read-only knowledge base viewing
3. **Administrators**: Full system control including user management, knowledge base editing, and analytics

---

## 2. SYSTEM ARCHITECTURE

### High-Level Architecture
```
┌─────────────────┐
│   Web Browser   │ (Frontend: HTML/JS/CSS)
└────────┬────────┘
         │ WebSocket + HTTP
         ▼
┌─────────────────┐
│  Login Server   │ (Port 7001 - FastAPI)
│  - Auth & CSRF  │
│  - Session Mgmt │
│  - WS Proxy     │
└────────┬────────┘
         │ WebSocket Proxy
         ▼
┌─────────────────┐
│   RAG Server    │ (Port 7000 - FastAPI)
│  - Voice ASR    │
│  - RAG Retrieval│
│  - Analytics    │
└────────┬────────┘
         │ HTTP (Ollama API)
         ▼
┌─────────────────┐
│     Ollama      │ (Port 11434)
│  - qwen2.5:3b   │
│  - GPU inference│
└─────────────────┘
         ▲
         │ HTTP (optional proxy)
┌─────────────────┐
│  Piper TTS      │ (Port 5002 - FastAPI microservice)
│  - CPU synthesis│
└─────────────────┘
```

### Technology Stack

#### Backend
- **FastAPI**: Async web framework for login, RAG, and Piper TTS services
- **Python 3.11**: Primary programming language
- **Ollama**: Local LLM runtime (OpenAI-compatible API, `qwen2.5:3b` on GPU)
- **faster-whisper**: CPU-based automatic speech recognition
- **Piper TTS**: CPU-based neural text-to-speech microservice (port 5002)
- **ChromaDB**: Vector database for RAG embeddings
- **Sentence-Transformers**: Text embedding model (all-MiniLM-L6-v2)
- **SQLite**: User database and analytics storage
- **aiohttp**: Async HTTP client for inter-service communication
- **Passlib**: Password hashing (bcrypt_sha256)
- **itsdangerous**: Cryptographic signing for sessions

#### Frontend
- **Vanilla JavaScript**: No frameworks, pure ES6+
- **WebSocket API**: Real-time bidirectional communication
- **Web Audio API**: Audio capture and processing
- **Piper TTS (server-side)**: Spoken responses streamed from RAG server
- **Chart.js**: Analytics visualization

#### ML/AI
- **qwen2.5:3b (Ollama)**: Local LLM for chat and RAG answers
- **all-MiniLM-L6-v2**: Embedding model for semantic search
- **faster-whisper-tiny.en**: Speech recognition model (CPU, int8)
- **Piper ONNX voices**: English and Arabic TTS voices

#### GPU
- **CUDA 12.x**: GPU acceleration for Ollama and RAG embeddings
- **NVIDIA RTX 3070 Laptop**: 8GB VRAM (typical dev target)
- **Ollama ggml-cuda backend**: LLM layer offloading managed by Ollama

---

## 3. PROJECT STRUCTURE & FILE DESCRIPTIONS

### Root Directory Files
```
├── project_start_server.py       # Main server launcher script
├── config.py                     # Centralized configuration (ports, secrets, paths)
├── requirements.txt              # Python package dependencies
├── README.md                     # Basic project documentation
├── sample_kb.txt                 # Sample knowledge base document
└── users.db                      # SQLite database for user accounts
```

**project_start_server.py**
- Entry point for launching all three servers
- Command-line arguments: `--enforce-gpu`, `--n-gpu-layers`
- Spawns Login Server (7001), RAG Server (7000), Piper TTS (5002)
- Requires Ollama running separately (`ollama serve`, model `qwen2.5:3b` pulled)
- Monitors server health and handles graceful shutdown
- Purpose: Single-command deployment of entire stack

**config.py**
- SESSION_SECRET: Cryptographic key for session cookies
- SESSION_COOKIE: Cookie name ("session")
- RAG_SERVER_URL: "http://127.0.0.1:7000"
- LLM_URL: "http://127.0.0.1:11434/api/chat" (Ollama native chat API)
- OLLAMA_MODEL: "qwen2.5:3b"
- LOGIN_SERVER_URL: "http://127.0.0.1:7001"
- Prevents hardcoded URLs across multiple files

**requirements.txt**
```
fastapi
uvicorn
faster-whisper
chromadb
sentence-transformers
aiohttp
passlib
itsdangerous
PyPDF2
pynvml  # GPU monitoring
```
(Ollama is installed separately; Piper runs via `tts_service/piper_server.py`.)

### Backend Directory (`backend/`)
```
backend/
├── __init__.py                   # Package marker
├── main_llm_server.py           # Optional Ollama proxy (port 8000; RAG calls Ollama directly)
├── assistify_rag_server.py      # Voice processing + RAG orchestration
├── voice_audio/                 # STT/TTS/WebSocket audio package
├── knowledge_base.py            # ChromaDB operations
├── load_documents.py            # Document ingestion script
├── database.py                  # SQLite schema and operations
├── analytics.py                 # Usage tracking and metrics
├── Models/                      # Local model storage
│   └── faster-whisper-tiny.en/  # ASR model (CPU)
├── assets/                      # Knowledge base documents
│   ├── sample_kb.txt
│   └── e2e_test.txt
├── chroma_db/                   # ChromaDB persistent storage
│   └── chroma.sqlite3
└── templates/                   # Legacy admin templates (unused)
    ├── admin_analytics.html
    ├── admin_errors.html
    └── admin_users.html
```

**main_llm_server.py** (Port 8000, optional)
- **Purpose**: Thin FastAPI wrapper around Ollama's OpenAI-compatible API
- **Note**: RAG server calls Ollama directly at `http://127.0.0.1:11434/api/chat`; this server is not required for normal operation
- **Key Functions**:
  - Health check against local Ollama model list
  - `POST /v1/chat/completions`: Forwards chat requests to Ollama (`qwen2.5:3b`)
- **Dependencies**: aiohttp, FastAPI (no llama-cpp-python)

**assistify_rag_server.py** (Port 7000)
- **Purpose**: Voice processing orchestrator and RAG query handler
- **Key Components**:
  - faster-whisper ASR initialization (CPU, mandatory)
  - Piper TTS client (HTTP to port 5002)
  - WebSocket handler for real-time audio streaming
  - RAG retrieval using ChromaDB similarity search
  - LLM queries via Ollama native chat API
  - Analytics tracking integration
- **Key Functions**:
  - `websocket_endpoint()`: Main WebSocket handler for voice chat
  - Voice audio delegated to `backend/voice_audio/` (STT, TTS, WS lifecycle)
  - `retrieve_relevant_context()`: Semantic search in knowledge base
  - `query_llm()`: HTTP POST to Ollama with RAG context
- **Audio Processing**:
  - Format: PCM16, 16kHz, mono
  - Buffering: Accumulates audio until silence or stop, then transcribes with faster-whisper
- **RAG Flow**:
  1. User voice → faster-whisper transcription (CPU)
  2. Transcription → ChromaDB embedding search (top results)
  3. Retrieved docs + query → LLM prompt template
  4. Ollama response → User (text + Piper TTS audio)
- **Dependencies**: faster-whisper, ChromaDB, aiohttp, sentence-transformers, Ollama

**knowledge_base.py**
- **Purpose**: ChromaDB vector database operations
- **Key Functions**:
  - `init_chroma()`: Initializes persistent ChromaDB client
  - `add_document(doc_id, text, metadata)`: Embeds and stores document
  - `query_documents(query_text, n_results=3)`: Semantic search
  - `list_all_documents()`: Returns all stored doc IDs
- **Embedding Model**: all-MiniLM-L6-v2 (384-dimensional vectors)
- **Collection**: "assistify_kb" (persistent)
- **Metadata**: Stores source filename, upload timestamp

**load_documents.py**
- **Purpose**: Bulk document ingestion CLI tool
- **Usage**: `python -m backend.load_documents`
- **Process**:
  1. Scans `backend/assets/` for .txt/.pdf files
  2. Extracts text (PyPDF2 for PDFs)
  3. Calls `add_document()` for each file
- **Use Case**: Initial knowledge base population

**database.py**
- **Purpose**: User authentication database schema
- **Tables**:
  - `users`: id, username, password_hash, role, mfa_enabled, mfa_secret, active
- **Functions**:
  - `init_user_db()`: Creates table with bootstrap superadmin
  - `verify_user(username, password)`: Credential validation
  - `create_user(username, password, role)`: New user creation
- **Default Credentials** (bootstrap only; see `Login_system/dev_users.py`):
  - superadmin:superadmin (role: superadmin)
- **Other roles** (Master Admin, Admin, Employee, Customer) are created via UI/API after bootstrap login.

**analytics.py**
- **Purpose**: Usage statistics and error logging
- **Database**: analytics.db (SQLite)
- **Tables**:
  - `usage_stats`: timestamp, username, user_role, query_text, response_status, error_message
- **Functions**:
  - `log_query(username, role, query, status, error)`: Records interaction
  - `get_analytics_summary()`: Aggregates usage by role
  - `get_recent_errors(limit=50)`: Retrieves error logs
- **Use Case**: Admin analytics dashboard data source

### Login System Directory (`Login_system/`)
```
Login_system/
├── login_server.py              # Authentication & session server (Port 7001)
└── templates/                   # Jinja2 HTML templates
    ├── Login.html               # Login page
    ├── main.html                # Customer dashboard
    ├── employee.html            # Employee dashboard (read-only KB access)
    ├── admin.html               # Admin dashboard
    ├── admin_users.html         # User management interface
    ├── admin_knowledge.html     # Knowledge base file manager
    └── admin_analytics.html     # Analytics visualization
```

**login_server.py** (Port 7001)
- **Purpose**: Central authentication gateway and frontend server
- **Key Responsibilities**:
  - User login/logout with session cookies
  - CSRF token validation
  - WebSocket proxy to RAG server (same-origin workaround)
  - Serves frontend static files with no-cache headers
  - Admin API endpoints for user/KB management
  - Employee read-only knowledge base access
- **Key Routes**:
  - `GET /`: Login page
  - `POST /login`: Authentication endpoint (redirects based on role)
  - `GET /admin`: Admin dashboard (requires admin role)
  - `GET /employee`: Employee dashboard (requires employee role)
  - `GET /main`: Customer dashboard
  - `GET /frontend/{path}`: Serves frontend files
  - `WebSocket /ws`: Proxies to RAG server WebSocket
- **Admin API Routes**:
  - `GET /api/users`: List all users (admin only)
  - `POST /api/users/create`: Create new user (admin only)
  - `POST /api/users/{id}/activate|deactivate`: Toggle user status (admin only)
  - `DELETE /api/users/{id}/delete`: Remove user (admin only)
  - `GET /api/knowledge/files`: List knowledge base files (admin + employee)
  - `GET /api/knowledge/files/{filename}`: Read file content (admin + employee)
  - `PUT /api/knowledge/files/{filename}`: Edit file content (admin only)
  - `DELETE /api/knowledge/files/{filename}`: Delete file (admin only)
  - `GET /api/knowledge/files/{filename}/download`: Download file (admin + employee)
  - `POST /proxy/upload_rag`: Upload document to knowledge base (admin only)
- **Session Management**:
  - URLSafeSerializer with SESSION_SECRET
  - httponly cookies (secure in production)
  - CSRF cookie (csrf_token) for form protection
  - Role-based redirection: admin → `/admin`, employee → `/employee`, customer → `/main`
- **Access Control Functions**:
  - `require_login(role)`: Requires specific role (strict match)
  - `require_role(*roles)`: Requires any of the specified roles (flexible)
  - `get_current_user()`: Extracts user from session cookie
- **WebSocket Proxy Flow**:
  1. Browser connects to `ws://127.0.0.1:7001/ws`
  2. Login server validates session cookie
  3. Opens client WebSocket to `ws://127.0.0.1:7000/ws`
  4. Bidirectional message forwarding (text and binary)
  5. Preserves same-origin policy for frontend
- **Dependencies**: FastAPI, Jinja2, passlib, itsdangerous

**templates/admin.html**
- **Purpose**: Main admin dashboard with section-based navigation
- **Sections**:
  - Quick Actions: Launch chat, Logout
  - Analytics & Monitoring: View analytics, View error logs
  - RAG System: Manage knowledge base, Upload documents
  - User Management: Manage users
- **Features**:
  - Responsive grid layout (mobile-friendly)
  - File upload with CSRF protection
  - Navigation functions to other admin pages
  - Dark theme UI (#232323 bg, #10a37f accent)

**templates/admin_users.html**
- **Purpose**: Complete user CRUD interface
- **Features**:
  - Create users with role selection (admin/customer/employee)
  - User list table: ID, username, role, status
  - Activate/Deactivate users
  - Delete users (cannot delete self)
  - Password minimum 8 characters
  - Real-time updates via fetch API
- **Security**: CSRF token required for all mutations

**templates/admin_knowledge.html**
- **Purpose**: Knowledge base file management
- **Features**:
  - List all .txt/.pdf files with size and modified date
  - Preview documents in modal (extracts PDF text)
  - Edit text files directly in browser
  - Download any document
  - Delete documents
  - Upload new documents
  - Re-indexes edited files into ChromaDB
- **File Operations**:
  - Read: Displays content in modal
  - Edit: Textarea editor, saves and re-indexes
  - Delete: Removes file from filesystem
  - Download: FileResponse with original filename
- **Security**: Path traversal protection (resolves and validates paths)

**templates/admin_analytics.html**
- **Purpose**: Visual analytics dashboard with charts
- **Features**:
  - Summary statistics: Total queries, success rate, total errors, active users
  - Pie chart: Usage by role (Chart.js doughnut)
  - Line chart: Error activity over last 24 hours
  - Recent errors table with timestamps
  - Auto-refresh every 30 seconds
  - Manual refresh button
- **Data Sources**:
  - `http://127.0.0.1:7000/analytics/summary`
  - `http://127.0.0.1:7000/analytics/errors`
- **Dependencies**: Chart.js 4.4.0 (CDN)

**templates/Login.html**
- **Purpose**: User authentication page
- **Features**:
  - Username/password form
  - Error message display (red banner)
  - Dark theme consistent with other pages
  - Autofocus on username field
  - Mobile-responsive layout

**templates/employee.html**
- **Purpose**: Dedicated dashboard for employee users
- **Features**:
  - Welcome message with employee badge (blue)
  - Launch chat assistant button
  - Read-only knowledge base table with preview/download
  - Document preview modal with full text display
  - Responsive design for mobile/tablet
  - **Restrictions**: Cannot edit, upload, or delete KB files
- **Actions Available**:
  - Preview KB documents in modal
  - Download KB documents
  - Access chat assistant
  - Logout

**templates/main.html**
- **Purpose**: Landing page for customer users
- **Features**:
  - Welcome message with username and role badge
  - "Launch Voice Chat Assistant" button → /frontend/index.html
  - Logout button
  - Dark theme matching admin pages

### Frontend Directory (`frontend/`)
```
frontend/
├── index.html                   # Main voice chat interface
└── Website_ChatGpt/             # Legacy/test files
    ├── Chatgpt_test.html
    └── rag_test.html
```

**index.html**
- **Purpose**: Real-time voice and text chat interface
- **Key Features**:
  - Voice recording with Start/Stop/Mute buttons
  - WebSocket communication for real-time transcription
  - Text-to-Speech with emoji filtering
  - Message history display (user and AI)
  - Audio buffer clearing to prevent bleed-through
- **Audio Processing**:
  - MediaRecorder API for microphone capture
  - AudioContext for PCM16 conversion (16kHz, mono)
  - Sends binary audio frames over WebSocket
  - Handles control messages to clear backend buffers
- **WebSocket Protocol**:
  - Binary messages: Audio data (PCM16)
  - Text messages: JSON control/transcript/response
    - `{type: 'control', action: 'stop_recording'}`: Clears buffers
    - `{type: 'transcript', text: '...'}`: User's transcribed speech
    - `{type: 'response', text: '...'}`: AI response
    - `{type: 'error', message: '...'}`: Error notification
- **TTS Implementation**:
  - Server-side Piper TTS via RAG WebSocket (audio chunks streamed from port 5002)
  - Client plays received PCM/WAV audio; browser Speech Synthesis API is not the primary path
- **Duplicate Message Fix**:
  - Removed client-side `appendMsg()` on form submit
  - Relies solely on server echo to display messages
  - Prevents same message appearing twice
- **CSS**: Dark theme (#232323), responsive layout, message bubbles

---

## 4. PROGRAM LOGIC & DATA FLOW

### Complete User Journey: Voice Query

#### Step 1: Authentication
1. User visits `http://127.0.0.1:7001/`
2. Login page loads (Login.html)
3. User submits username/password
4. POST /login → `login_server.py` validates credentials
5. Creates session cookie with URLSafeSerializer
6. Sets CSRF cookie for form protection
7. Redirects to `/admin` (admin role) or `/main` (other roles)

#### Step 2: Dashboard Access
1. User redirected based on role after login:
   - Admin → `/admin` (full dashboard with all controls)
   - Employee → `/employee` (chat + read-only KB viewer)
   - Customer → `/main` (chat access only)
2. Dashboard loads with role-specific features
3. Employee dashboard loads KB file list via `GET /api/knowledge/files`
4. Employee can preview/download but cannot edit/delete files

#### Step 3: Chat Interface Access
1. User clicks "Launch Chat Assistant" button
2. Navigates to `/frontend/index.html`
3. Login server serves file with no-cache headers
4. JavaScript loads, connects WebSocket to `/ws`
5. Login server validates session cookie
6. Opens proxy WebSocket to RAG server at `ws://127.0.0.1:7000/ws`

#### Step 4: Voice Recording Start
1. User clicks "Start Recording" button
2. JavaScript requests microphone permission
3. MediaRecorder starts capturing audio
4. AudioContext converts to PCM16 (16kHz, mono)
5. Audio chunks sent as binary WebSocket messages
6. RAG server receives audio frames, buffers them

#### Step 5: Speech Recognition (ASR)
1. RAG server accumulates audio in buffer
2. On silence or stop, sends PCM16 audio to faster-whisper (CPU)
3. faster-whisper transcribes with VAD filtering
4. Sends `{type: 'transcript', text: 'User's question'}` to frontend

#### Step 6: RAG Retrieval
1. RAG server receives final transcription
2. Calls `retrieve_relevant_context(query_text)`
3. Embeds query with all-MiniLM-L6-v2
4. ChromaDB performs cosine similarity search
5. Returns top 3 most relevant document chunks
6. Constructs prompt template:
   ```
   Use the following context to answer the question.
   Context: [Retrieved docs]
   Question: [User's question]
   Answer:
   ```

#### Step 7: LLM Inference
1. RAG server sends POST to Ollama at `http://127.0.0.1:11434/api/chat`
2. Request body includes `model: "qwen2.5:3b"`, messages, and context options
3. Ollama runs inference on GPU (ggml-cuda)
4. Returns assistant message text to RAG server

#### Step 8: Response Delivery
1. RAG server receives LLM response
2. Logs interaction to analytics.db (username, query, status)
3. Sends `{type: 'response', text: 'AI answer'}` over WebSocket
4. Login server proxies message to browser
5. Frontend JavaScript receives response
6. Displays message in chat history
7. Piper TTS synthesizes spoken audio (server-side, port 5002)
8. Audio streamed to browser over WebSocket

#### Step 9: Recording Stop
1. User clicks "Stop Recording" button
2. Frontend sends `{type: 'control', action: 'stop_recording'}`
3. RAG server clears audio buffer and STT state
5. Prevents audio bleed-through on next recording

### Error Handling Flow

#### LLM / Ollama Failure
1. Ollama not running or model not pulled
2. RAG server receives connection error from Ollama API
3. Logs error to analytics.db
4. Sends `{type: 'error', message: 'LLM unavailable'}` to frontend
5. Fix: `ollama serve` and `ollama pull qwen2.5:3b`

#### ASR Failure
1. faster-whisper model path missing
2. RAG server fails STT initialization on startup
3. User sees transcription errors or empty transcripts
4. Fix: ensure `backend/Models/faster-whisper-tiny.en/` exists

#### Authentication Failure
1. Invalid session cookie
2. `get_current_user()` returns None
3. WebSocket connection rejected with code 1008
4. Frontend shows "Authentication failed" error

---

## 5. TECHNOLOGIES & LIBRARIES - DETAILED RATIONALE

### Why Ollama?
- **Simple deployment**: Pull model once (`ollama pull qwen2.5:3b`), no GGUF shard management
- **GPU offloading**: Ollama manages layer placement via ggml-cuda
- **Low VRAM**: 3B model fits comfortably alongside RAG embeddings on 8GB GPUs
- **OpenAI-compatible API**: Easy integration from RAG server
- **Alternative rejected**: In-process llama-cpp-python (more fragile builds, larger ops burden)

### Why faster-whisper for ASR?
- **CPU-based**: Keeps GPU VRAM free for Ollama and sentence-transformers
- **Offline**: No cloud ASR API calls (data privacy)
- **Accurate**: Better than legacy Vosk on natural speech
- **VAD built-in**: Voice activity detection filters silence
- **Lightweight**: tiny.en model for low-latency dev setups

### Why Piper TTS?
- **CPU-only**: Does not compete with Ollama for GPU memory
- **Fast**: ONNX runtime, suitable for real-time reply playback
- **Self-hosted**: No external TTS API dependency
- **Microservice**: Isolated on port 5002 (`tts_service/piper_server.py`)

### Why ChromaDB?
- **Simplicity**: No server setup, embedded Python library
- **Persistence**: SQLite-backed storage (chroma.sqlite3)
- **Embeddings**: Built-in support for sentence-transformers
- **Semantic Search**: Cosine similarity out of the box
- **Fast**: Adequate for <10k documents
- **Alternative**: Weaviate/Qdrant would be overkill for this scale

### Why FastAPI?
- **Async/Await**: Native async WebSocket and HTTP handling
- **Type Safety**: Pydantic models for request/response validation
- **Auto Docs**: Swagger UI at /docs (development)
- **Performance**: Comparable to Node.js, faster than Flask
- **WebSocket**: First-class WebSocket support (vs Flask-SocketIO complexity)

### Why Vanilla JavaScript?
- **No Build Step**: Direct browser loading, no webpack/vite
- **Simplicity**: Easy to debug, no framework learning curve
- **WebSocket API**: Native browser support
- **Web Audio API**: Direct access to microphone
- **Fast Iteration**: Refresh browser, see changes immediately
- **Alternative Rejected**: React would add complexity without benefit

### Why Three Separate Servers?
- **Separation of Concerns**: Auth, Voice, LLM are independent services
- **Scalability**: Can scale LLM server separately (multiple GPUs)
- **Security**: Auth layer isolates LLM from direct external access
- **Failure Isolation**: LLM crash doesn't kill auth server
- **Development**: Can restart LLM server without logging out users
- **Role-Based Access**: Auth server enforces different permissions per role

---

## 6. EXTERNAL DEPENDENCIES & SERVICES

### Required System Libraries
- **CUDA Toolkit 12.x**: GPU driver and runtime (for Ollama and PyTorch embeddings)
- **Ollama**: Local LLM runtime (separate install from Python deps)
- **SQLite3**: Database engine (usually pre-installed)

### Python Package Dependencies (requirements.txt)
```
fastapi>=0.104.0           # Web framework
uvicorn[standard]>=0.24.0  # ASGI server
faster-whisper>=1.0.0      # Speech recognition (CPU)
chromadb>=0.4.18           # Vector database
sentence-transformers>=2.2.2  # Embedding model
aiohttp>=3.9.0             # Async HTTP client
passlib>=1.7.4             # Password hashing
itsdangerous>=2.1.2        # Session signing
PyPDF2>=3.0.1              # PDF text extraction
pynvml>=11.5.0             # GPU monitoring
jinja2>=3.1.2              # Template engine
python-multipart>=0.0.6    # File upload support
piper-tts                  # Piper TTS (also via tts_service microservice)
```

### External APIs & Services
**None for core inference** — LLM, ASR, TTS, and RAG run locally. Optional: Google OAuth, EmailJS for OTP.

### AI Models (Downloaded Separately)
1. **qwen2.5:3b (Ollama)**
   - Install: `ollama pull qwen2.5:3b`
   - Managed by Ollama under `~/.ollama/models/` (not in repo)

2. **faster-whisper-tiny.en**
   - Location: `backend/Models/faster-whisper-tiny.en/`
   - Device: CPU, compute type int8

3. **Piper ONNX voices**
   - Location: configured via `PIPER_*_VOICE_PATH` env vars
   - Served by `tts_service/piper_server.py` on port 5002

4. **all-MiniLM-L6-v2** (Auto-downloaded by sentence-transformers)
   - Source: Hugging Face (sentence-transformers/all-MiniLM-L6-v2)
   - Size: ~90 MB
   - Cache: `~/.cache/huggingface/`

---

## 7. CONFIGURATION & ENVIRONMENT

### Required Hardware
- **GPU**: NVIDIA GPU with 6GB+ VRAM (tested on RTX 3070 Laptop 8GB)
- **RAM**: 8GB+ system RAM
- **CPU**: 4+ cores recommended for faster-whisper ASR and Piper TTS
- **Storage**: 10GB for models + data

### GPU Configuration
- **CUDA Version**: 12.x (driver compatible with Ollama)
- **VRAM**: Ollama (`qwen2.5:3b`) + RAG embeddings share GPU; STT/TTS stay on CPU

### Environment Variables (Optional)
```bash
OLLAMA_MODEL=qwen2.5:3b    # Must match `ollama list`
WHISPER_MODEL_PATH=...     # faster-whisper model directory
SESSION_SECRET=<random>    # Override session key
CUDA_VISIBLE_DEVICES=0     # Select GPU for Ollama
IS_PRODUCTION=1            # Disable dev login fallbacks
```

### Port Configuration
- **7001**: Login/Auth server (external access)
- **7000**: RAG server (internal only, proxied via 7001)
- **11434**: Ollama API (local LLM)
- **5002**: Piper TTS microservice (optional, started by launcher)
- **8000**: Optional Ollama proxy (`main_llm_server.py`; not required)

### Database Files
- `users.db`: User accounts (SQLite)
- `analytics.db`: Usage logs (SQLite)
- `backend/chroma_db/chroma.sqlite3`: Vector embeddings (ChromaDB)

---

## 8. KNOWN ISSUES & LIMITATIONS

### Active Issues
1. **Employee Analytics**: Employees cannot view their own usage statistics
   - **Impact**: No self-service performance tracking
   - **Fix**: Add `/employee/analytics` page with user-scoped data

2. **No HTTPS**: Uses HTTP in development, cookies not secure
   - **Impact**: Session hijacking risk on untrusted networks
   - **Fix**: Deploy behind nginx with SSL certificates

3. **Hardcoded URLs**: Some inter-service URLs hardcoded
   - **Location**: `frontend/index.html` WebSocket URL
   - **Fix**: Use environment variables or config.js

4. **No Rate Limiting**: Vulnerable to abuse (unlimited API calls)
   - **Impact**: Server overload, GPU saturation
   - **Fix**: Implement rate limiting middleware (slowapi)

5. **Single GPU Only**: Cannot distribute load across multiple GPUs
   - **Fix**: Use vLLM or Ray Serve for multi-GPU inference

6. **No Pagination**: User/document lists load all records
   - **Impact**: Slow performance with 1000+ users/documents
   - **Fix**: Implement server-side pagination

7. **PDF Extraction Errors**: Some PDFs fail to parse (PyPDF2 limitations)
   - **Fix**: Use pdfminer.six or unstructured for better extraction

8. **No Document Versioning**: Editing KB file overwrites without history
   - **Fix**: Implement version control or backup before edit

9. **CSRF Token Rotation**: CSRF token never rotates, set once on login
   - **Security**: Vulnerable to long-lived token theft
   - **Fix**: Rotate CSRF token periodically

### TODOs (Incomplete Features)
1. **Employee Analytics Dashboard**: Employees cannot view their personal usage stats
2. **Password Reset**: No forgot password functionality
3. **MFA Enforcement**: MFA code exists but not enforced in UI
4. **Email Notifications**: No email alerts for errors/events
5. **Backup/Restore**: No database backup automation
6. **Logging Configuration**: Logs go to stdout, no rotation
7. **Health Check Endpoint**: No `/health` or `/ready` endpoints
8. **API Documentation**: No Swagger annotations for admin APIs
9. **Unit Tests**: Zero test coverage
10. **Docker Support**: No Dockerfile or docker-compose.yml
11. **Monitoring**: No Prometheus metrics or Grafana dashboards
12. **Conversation History**: Employees cannot review customer interaction logs

### Performance Limitations
1. **LLM Context Window**: 4096 tokens (can't handle long documents)
2. **RAG Top-K**: Fixed at 3 results (no dynamic adjustment)
3. **Audio Buffering**: Fixed 16kHz, no adaptive quality
4. **Concurrent Users**: Untested with >10 simultaneous connections
5. **Vector Search**: No approximate nearest neighbor (exact search only)

### Security Concerns
1. **Bootstrap Credentials**: Only `superadmin/superadmin` is seeded in `Login_system/dev_users.py` — change before production
2. **SQL Injection**: Direct SQLite queries without parameterization in some places
3. **Path Traversal**: File operations rely on path resolution (potential bypass)
4. **XSS**: User-generated content not sanitized before display
5. **Session Fixation**: Session ID not regenerated after login

---

## 9. DEPLOYMENT GUIDE

### Development Deployment
```bash
# 1. Install CUDA drivers and Ollama (https://ollama.com)
ollama serve
ollama pull qwen2.5:3b

# 2. Create conda environment
conda env create -f environment_main.yml
conda activate assistify_main

# 3. Install Python dependencies (if not already in env)
pip install -r requirements.txt

# 4. Seed dev users
python Login_system/init_users_db.py

# 5. Ensure faster-whisper model exists at backend/Models/faster-whisper-tiny.en/

# 6. Start stack
python start_main_servers.py

# 7. (Optional) Populate knowledge base
python -m backend.load_documents
```

### Production Deployment Recommendations
1. **Reverse Proxy**: nginx with SSL termination
2. **Process Manager**: systemd or supervisord
3. **Environment**: Use .env file for secrets
4. **Logging**: Configure file logging with rotation
5. **Monitoring**: Add Prometheus + Grafana
6. **Backups**: Daily SQLite dumps, weekly ChromaDB snapshots
7. **Rate Limiting**: nginx limit_req or slowapi middleware
8. **Firewall**: Close ports 7000, 11434, and 5002 externally (expose 7001 via reverse proxy only)

---

## 10. TESTING & VALIDATION

### Manual Testing Checklist
- [ ] User can login with superadmin/superadmin
- [ ] Superadmin can create tenants and staff via UI/API
- [ ] Admin redirects to `/admin` dashboard (after created by superadmin)
- [ ] Employee redirects to `/employee` dashboard (after created by admin)
- [ ] Customer redirects to `/main` dashboard (after registration or staff creation)
- [ ] Chat interface loads and WebSocket connects
- [ ] Voice recording captures audio
- [ ] ASR correctly transcribes speech
- [ ] LLM generates relevant responses
- [ ] Piper TTS audio plays for assistant responses
- [ ] Admin can create/edit/delete users
- [ ] Admin can upload/edit/delete KB documents
- [ ] Employee can view KB documents (read-only)
- [ ] Employee can preview KB documents
- [ ] Employee can download KB documents
- [ ] Employee CANNOT edit/delete KB documents
- [ ] Analytics dashboard shows charts (admin only)
- [ ] Error logs appear in admin panel (admin only)
- [ ] Logout properly invalidates session

### Performance Benchmarks
- **LLM Latency**: ~2-3 seconds for 256 tokens (RTX 3070)
- **ASR Latency**: <500ms for 3-second audio clip
- **WebSocket Roundtrip**: <50ms on localhost
- **RAG Retrieval**: <100ms for 1000 documents

### Known Test Files
- `scripts/e2e_test.py`: End-to-end voice query test
- `scripts/e2e_test_client.py`: WebSocket test client
- `scripts/test_ws_connect.py`: WebSocket connection test
- `scripts/import_test.py`: Module import validation

---

## 11. FUTURE ENHANCEMENTS

### Planned Features
1. **Employee Analytics**: Personal usage stats and performance metrics
2. **Customer Interaction History**: Employees review conversation logs
3. **Multi-language Support**: Add i18n for UI and ASR
4. **Voice Cloning**: Custom TTS voices per user
5. **Advanced RAG**: Re-ranking, query expansion, hybrid search
6. **Mobile App**: Native iOS/Android apps
7. **SSO Integration**: SAML/OAuth2 for enterprise auth
8. **Conversation History**: Persistent chat logs per user
9. **Fine-tuned Models**: Custom-trained LLM on domain data
10. **A/B Testing**: Compare different prompts/models
11. **Export Reports**: PDF/CSV analytics exports
12. **API Gateway**: External API access with rate limits
13. **Employee Permissions**: Granular permission system per employee

### Scalability Roadmap
1. **Horizontal Scaling**: Multiple LLM server replicas
2. **Load Balancing**: nginx upstream for LLM servers
3. **Caching**: Redis for frequent queries
4. **CDN**: Static asset delivery
5. **Database**: PostgreSQL for user data (vs SQLite)
6. **Vector DB**: Migrate to Qdrant for >100k documents
7. **Streaming**: Server-Sent Events for token streaming
8. **Microservices**: Separate ASR, RAG, LLM into containers

---

## 12. TROUBLESHOOTING GUIDE

### Common Errors

**"CUDA out of memory"**
- **Cause**: GPU VRAM exhausted (Ollama + embeddings)
- **Fix**: Use smaller Ollama model or reduce concurrent RAG embedding load

**"faster-whisper model not found"**
- **Cause**: Missing ASR model directory
- **Fix**: Download or place model at `backend/Models/faster-whisper-tiny.en/`

**"Ollama unreachable" / LLM errors**
- **Cause**: Ollama not running or `qwen2.5:3b` not pulled
- **Fix**: `ollama serve` and `ollama pull qwen2.5:3b`

**"Piper TTS unavailable"**
- **Cause**: Piper microservice not running on port 5002
- **Fix**: Start via launcher or `start_piper_service.bat`

**"ChromaDB corrupted"**
- **Cause**: chroma.sqlite3 database file damaged
- **Fix**: Delete `backend/chroma_db/`, re-run `load_documents.py`

**"Analytics charts not loading"**
- **Cause**: CORS blocking Chart.js CDN
- **Fix**: Check browser console, ensure internet access for CDN

---

## 13. PROJECT METRICS

### Lines of Code (Approximate)
- **Backend Python**: ~3,700 lines
- **Frontend JavaScript**: ~650 lines
- **HTML/CSS**: ~2,300 lines
- **Total**: ~6,650 lines

### File Count
- **Python files**: 12
- **HTML templates**: 9
- **JavaScript files**: 4
- **Total files**: ~51 (excluding models)

### Development Timeline
- **Initial prototype**: 2 weeks
- **Voice integration**: 1 week
- **Admin dashboard**: 1 week
- **Employee role implementation**: 0.5 weeks
- **Bug fixes & optimization**: 1 week
- **Total**: ~5.5 weeks

---

## 14. GLOSSARY

**RAG**: Retrieval-Augmented Generation - combines search with LLM generation  
**ASR**: Automatic Speech Recognition - converts speech to text  
**TTS**: Text-to-Speech - converts text to spoken audio  
**LLM**: Large Language Model - neural network trained on text  
**Ollama**: Local LLM runtime used for `qwen2.5:3b` inference  
**CUDA**: Compute Unified Device Architecture - NVIDIA GPU programming  
**VRAM**: Video RAM - GPU memory  
**CSRF**: Cross-Site Request Forgery - session security attack  
**PCM16**: Pulse Code Modulation, 16-bit - raw audio format  
**ChromaDB**: Embeddings database for vector similarity search  
**faster-whisper**: CTranslate2-based Whisper implementation for ASR  
**Piper**: Lightweight ONNX neural TTS engine  
**FastAPI**: Modern Python web framework  
**WebSocket**: Full-duplex communication protocol  

---

## 15. CONTACT & SUPPORT

### Documentation References
- FastAPI: https://fastapi.tiangolo.com/
- Ollama: https://ollama.com/
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Piper: https://github.com/rhasspy/piper
- ChromaDB: https://docs.trychroma.com/
- Qwen2.5: https://ollama.com/library/qwen2.5

### Project Structure Summary
```
Assistify Voice Help Desk
├── Authentication Layer (Login Server - Port 7001)
├── Voice + RAG Layer (RAG Server - Port 7000)
├── LLM Runtime (Ollama - Port 11434, qwen2.5:3b)
├── TTS Microservice (Piper - Port 5002)
└── Frontend Interface (Browser - WebSocket + HTTP)
```

## 16. ROLE-BASED ACCESS CONTROL MATRIX

| Feature | Admin | Employee | Customer |
|---------|-------|----------|----------|
| Login/Logout | ✅ | ✅ | ✅ |
| Chat Assistant | ✅ | ✅ | ✅ |
| View KB Documents | ✅ | ✅ | ❌ |
| Download KB Documents | ✅ | ✅ | ❌ |
| Preview KB Documents | ✅ | ✅ | ❌ |
| Upload KB Documents | ✅ | ❌ | ❌ |
| Edit KB Documents | ✅ | ❌ | ❌ |
| Delete KB Documents | ✅ | ❌ | ❌ |
| View Analytics | ✅ | ❌ | ❌ |
| View Error Logs | ✅ | ❌ | ❌ |
| Create Users | ✅ | ❌ | ❌ |
| Edit Users | ✅ | ❌ | ❌ |
| Delete Users | ✅ | ❌ | ❌ |
| Activate/Deactivate Users | ✅ | ❌ | ❌ |
| Dashboard Path | `/admin` | `/employee` | `/main` |

### Access Control Implementation
- **Admin**: Full system access via `require_login("admin")`
- **Employee**: Chat + read-only KB via `require_role("admin", "employee")`
- **Customer**: Chat only via `require_login()` (any authenticated user)

---

**End of Project Briefing**
**Last Updated**: November 17, 2025
**Version**: 1.1 (Employee Role Implementation)
