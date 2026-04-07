# Assistify - AI-Powered Voice Help Desk System
## Complete Project Briefing & Technical Documentation

---

## 1. SYSTEM OVERVIEW

### Project Purpose
Assistify is an enterprise-grade AI-powered help desk system that provides real-time voice and text-based customer support using advanced Retrieval-Augmented Generation (RAG) technology. The system combines automatic speech recognition, large language model inference, and knowledge base retrieval to deliver accurate, context-aware responses to user queries.

### Core Capabilities
- **Voice-to-Voice Interaction**: Users speak questions, receive spoken AI responses
- **Real-time ASR**: Automatic Speech Recognition using Vosk (CPU-based)
- **GPU-Accelerated LLM**: Qwen2.5-7B-Instruct model running on NVIDIA GPU
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
         │ HTTP REST API
         ▼
┌─────────────────┐
│   LLM Server    │ (Port 8000 - FastAPI)
│  - GPU Inference│
│  - Qwen2.5-7B   │
└─────────────────┘
```

### Technology Stack

#### Backend
- **FastAPI**: Async web framework for all three servers
- **Python 3.11**: Primary programming language
- **llama-cpp-python (CUDA)**: GPU-accelerated LLM inference
- **Vosk**: CPU-based automatic speech recognition
- **ChromaDB**: Vector database for RAG embeddings
- **Sentence-Transformers**: Text embedding model (all-MiniLM-L6-v2)
- **SQLite**: User database and analytics storage
- **aiohttp**: Async HTTP client for inter-service communication
- **Passlib**: Password hashing (pbkdf2_sha256)
- **itsdangerous**: Cryptographic signing for sessions

#### Frontend
- **Vanilla JavaScript**: No frameworks, pure ES6+
- **WebSocket API**: Real-time bidirectional communication
- **Web Audio API**: Audio capture and processing
- **Speech Synthesis API**: Text-to-speech output
- **Chart.js**: Analytics visualization

#### ML/AI
- **Qwen2.5-7B-Instruct-Q4_K_M**: Quantized LLM (4.36 GiB VRAM)
- **all-MiniLM-L6-v2**: Embedding model for semantic search
- **Vosk-model-en-us-0.22-lgraph**: Speech recognition acoustic model

#### GPU
- **CUDA 12.4**: GPU acceleration framework
- **NVIDIA RTX 3070 Laptop**: 8GB VRAM, compute capability 8.6
- **llama.cpp CUDA backend**: Direct GPU kernel execution

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
- Spawns Login Server (7001), RAG Server (7000), LLM Server (8000)
- Monitors server health and handles graceful shutdown
- Purpose: Single-command deployment of entire stack

**config.py**
- SESSION_SECRET: Cryptographic key for session cookies
- SESSION_COOKIE: Cookie name ("session")
- RAG_SERVER_URL: "http://127.0.0.1:7000"
- LLM_SERVER_URL: "http://0.0.0.0:8000"
- LOGIN_SERVER_URL: "http://127.0.0.1:7001"
- Prevents hardcoded URLs across multiple files

**requirements.txt**
```
fastapi
uvicorn
llama-cpp-python  # Must be CUDA-enabled build
vosk
chromadb
sentence-transformers
aiohttp
passlib
itsdangerous
PyPDF2
pynvml  # GPU monitoring
```

### Backend Directory (`backend/`)
```
backend/
├── __init__.py                   # Package marker
├── main_llm_server.py           # LLM inference server (GPU-only)
├── assistify_rag_server.py      # Voice processing + RAG orchestration
├── knowledge_base.py            # ChromaDB operations
├── load_documents.py            # Document ingestion script
├── database.py                  # SQLite schema and operations
├── analytics.py                 # Usage tracking and metrics
├── Models/                      # AI model storage
│   ├── Qwen2.5-7B-LLM/         # LLM GGUF files (2 shards)
│   └── vosk-model-en-us-0.22-lgraph/  # ASR acoustic model
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

**main_llm_server.py** (Port 8000)
- **Purpose**: GPU-only LLM inference service
- **Key Functions**:
  - `load_llm_model()`: Loads Qwen2.5-7B with 40 GPU layers, n_ctx=4096
  - `POST /generate`: Accepts prompt, returns completion
  - `on_startup()`: Validates GPU availability, raises RuntimeError if missing
- **GPU Enforcement**: No CPU fallback, strict CUDA requirement
- **Memory Management**: KV cache reset via `llm.reset()` before each request
- **Error Handling**: Returns `{"error": "..."}` JSON on failures
- **Dependencies**: llama-cpp-python (CUDA), torch, pynvml

**assistify_rag_server.py** (Port 7000)
- **Purpose**: Voice processing orchestrator and RAG query handler
- **Key Components**:
  - Vosk ASR initialization (mandatory, raises FileNotFoundError if missing)
  - WebSocket handler for real-time audio streaming
  - RAG retrieval using ChromaDB similarity search
  - LLM query proxy to main_llm_server
  - Analytics tracking integration
- **Key Functions**:
  - `websocket_endpoint()`: Main WebSocket handler for voice chat
  - `handle_audio_frame()`: PCM16 audio processing with Vosk
  - `retrieve_relevant_context()`: Semantic search in knowledge base
  - `query_llm()`: HTTP POST to LLM server with RAG context
  - `handle_control_message()`: Clears audio buffers on recording stop
- **Audio Processing**:
  - Format: PCM16, 16kHz, mono
  - Buffering: Accumulates audio chunks until silence or stop
  - Vosk recognizer with word-level timestamps enabled
- **RAG Flow**:
  1. User voice → ASR transcription
  2. Transcription → ChromaDB embedding search (top 3 results)
  3. Retrieved docs + query → LLM prompt template
  4. LLM response → User (text + optional TTS)
- **Dependencies**: Vosk, ChromaDB, aiohttp, sentence-transformers

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
  - `init_user_db()`: Creates table with default users (admin/employee/customer)
  - `verify_user(username, password)`: Credential validation
  - `create_user(username, password, role)`: New user creation
- **Default Credentials**:
  - admin:admin123 (role: admin)
  - employee:employee123 (role: employee)
  - customer:customer123 (role: customer)

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
  - `speakText(text)`: Strips emojis with regex, uses SpeechSynthesis API
  - Emoji regex: `[\u{1F300}-\u{1F9FF}\u{1F600}-\u{1F64F}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]`
  - Prevents "smiley face" being spoken instead of displaying 😊
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
1. RAG server accumulates audio in `audio_buffer`
2. Feeds chunks to Vosk recognizer
3. Vosk processes acoustic features, updates decoding state
4. On partial results, updates frontend with interim text
5. On final result (silence or stop), completes transcription
6. Sends `{type: 'transcript', text: 'User's question'}` to frontend

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
1. RAG server sends POST to `http://0.0.0.0:8000/generate`
2. Request body: `{prompt: "...", max_tokens: 256, temperature: 0.7}`
3. LLM server resets KV cache (`llm.reset()`)
4. Calls `llm(prompt, max_tokens=256, temperature=0.7, stop=["User:", "\n\n"])`
5. GPU executes inference (40 layers on RTX 3070)
6. Streams tokens back to RAG server
7. Returns `{text: "AI's response"}`

#### Step 8: Response Delivery
1. RAG server receives LLM response
2. Logs interaction to analytics.db (username, query, status)
3. Sends `{type: 'response', text: 'AI answer'}` over WebSocket
4. Login server proxies message to browser
5. Frontend JavaScript receives response
6. Displays message in chat history
7. Calls `speakText(response)` for TTS
8. Speech Synthesis API speaks the answer (emojis filtered)

#### Step 9: Recording Stop
1. User clicks "Stop Recording" button
2. Frontend sends `{type: 'control', action: 'stop_recording'}`
3. RAG server clears `audio_buffer`
4. Resets Vosk recognizer to fresh state
5. Prevents audio bleed-through on next recording

### Error Handling Flow

#### LLM Server Failure
1. LLM server cannot load model or GPU fails
2. Returns `{error: "GPU initialization failed"}`
3. RAG server detects error key in response
4. Logs error to analytics.db
5. Sends `{type: 'error', message: 'LLM unavailable'}` to frontend
6. Frontend displays error message to user

#### ASR Failure
1. Vosk model file missing
2. RAG server raises FileNotFoundError on startup
3. Server crashes (intentional fail-fast)
4. User sees "Cannot connect to server" in frontend

#### Authentication Failure
1. Invalid session cookie
2. `get_current_user()` returns None
3. WebSocket connection rejected with code 1008
4. Frontend shows "Authentication failed" error

---

## 5. TECHNOLOGIES & LIBRARIES - DETAILED RATIONALE

### Why llama-cpp-python (CUDA)?
- **Quantized Model Support**: Runs Q4_K_M GGUF files (4-bit quantization)
- **Low VRAM**: 4.36 GiB fits in 8GB RTX 3070 Laptop
- **Fast Inference**: Direct CUDA kernels, no PyTorch overhead
- **CPU Fallback**: Removed intentionally to enforce GPU-only
- **Metal/CUDA/OpenCL**: Cross-platform GPU support (using CUDA here)
- **Alternative Rejected**: Hugging Face Transformers (requires 16GB+ VRAM for 7B FP16)

### Why Vosk for ASR?
- **CPU-Based**: Offloads ASR from GPU, reserves GPU for LLM
- **Offline**: No API calls to Google/Azure (data privacy)
- **Accurate**: Tested by user, correctly transcribes "Talk about Cristiano Ronaldo"
- **Streaming**: Supports partial results for real-time feedback
- **Lightweight**: 500MB model vs 3GB+ for Whisper large
- **Alternative Rejected**: Faster-Whisper small (inaccurate: "So, come out Christiano Ronaldo")

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
- **CUDA Toolkit 12.4**: GPU driver and runtime
- **cuBLAS, cuDNN**: CUDA math libraries for llama.cpp
- **PortAudio**: Audio I/O library (for Vosk)
- **SQLite3**: Database engine (usually pre-installed)

### Python Package Dependencies (requirements.txt)
```
fastapi>=0.104.0           # Web framework
uvicorn[standard]>=0.24.0  # ASGI server
llama-cpp-python>=0.3.4    # MUST be CUDA build: CMAKE_ARGS="-DLLAMA_CUDA=on"
vosk>=0.3.45               # Speech recognition
chromadb>=0.4.18           # Vector database
sentence-transformers>=2.2.2  # Embedding model
aiohttp>=3.9.0             # Async HTTP client
passlib>=1.7.4             # Password hashing
itsdangerous>=2.1.2        # Session signing
PyPDF2>=3.0.1              # PDF text extraction
pynvml>=11.5.0             # GPU monitoring
jinja2>=3.1.2              # Template engine
python-multipart>=0.0.6    # File upload support
```

### External APIs & Services
**None** - System is fully self-hosted and offline-capable

### AI Models (Downloaded Separately)
1. **Qwen2.5-7B-Instruct-Q4_K_M** (4.36 GiB)
   - Source: Hugging Face (bartowski/Qwen2.5-7B-Instruct-GGUF)
   - Files: 2 shards (00001-of-00002.gguf, 00002-of-00002.gguf)
   - Location: `backend/Models/Qwen2.5-7B-LLM/`

2. **vosk-model-en-us-0.22-lgraph** (500 MB)
   - Source: alphacephei.com/vosk/models
   - Contents: Kaldi acoustic model + language graph
   - Location: `backend/Models/vosk-model-en-us-0.22-lgraph/`

3. **all-MiniLM-L6-v2** (Auto-downloaded by sentence-transformers)
   - Source: Hugging Face (sentence-transformers/all-MiniLM-L6-v2)
   - Size: ~90 MB
   - Cache: `~/.cache/huggingface/`

---

## 7. CONFIGURATION & ENVIRONMENT

### Required Hardware
- **GPU**: NVIDIA GPU with 6GB+ VRAM (tested on RTX 3070 Laptop 8GB)
- **RAM**: 8GB+ system RAM
- **CPU**: 4+ cores recommended for Vosk ASR
- **Storage**: 10GB for models + data

### GPU Configuration
- **CUDA Version**: 12.4 (driver 552.44+)
- **Compute Capability**: 7.0+ (tested on 8.6)
- **GPU Layers**: 40 (offloads entire Qwen2.5-7B model)
- **VRAM Usage**: ~4.5 GB (model) + 500 MB (KV cache)

### Environment Variables (Optional)
```bash
USE_WHISPER=0              # Force Vosk (default)
SESSION_SECRET=<random>    # Override session key
CUDA_VISIBLE_DEVICES=0     # Select GPU
```

### Port Configuration
- **7001**: Login/Auth server (external access)
- **7000**: RAG server (internal only, proxied via 7001)
- **8000**: LLM server (internal only)

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
1. **Default Credentials**: admin:admin123 shipped in production
2. **SQL Injection**: Direct SQLite queries without parameterization in some places
3. **Path Traversal**: File operations rely on path resolution (potential bypass)
4. **XSS**: User-generated content not sanitized before display
5. **Session Fixation**: Session ID not regenerated after login

---

## 9. DEPLOYMENT GUIDE

### Development Deployment
```bash
# 1. Install CUDA 12.4 and cuDNN
# 2. Create conda environment
conda create -n grad python=3.11
conda activate grad

# 3. Install llama-cpp-python with CUDA
CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir

# 4. Install other dependencies
pip install -r requirements.txt

# 5. Download models
# - Qwen2.5-7B GGUF → backend/Models/Qwen2.5-7B-LLM/
# - Vosk model → backend/Models/vosk-model-en-us-0.22-lgraph/

# 6. Initialize databases
python -m backend.database  # Creates users.db
python -m backend.load_documents  # Populates ChromaDB

# 7. Launch servers
python project_start_server.py --enforce-gpu --n-gpu-layers 40
```

### Production Deployment Recommendations
1. **Reverse Proxy**: nginx with SSL termination
2. **Process Manager**: systemd or supervisord
3. **Environment**: Use .env file for secrets
4. **Logging**: Configure file logging with rotation
5. **Monitoring**: Add Prometheus + Grafana
6. **Backups**: Daily SQLite dumps, weekly ChromaDB snapshots
7. **Rate Limiting**: nginx limit_req or slowapi middleware
8. **Firewall**: Close ports 7000 and 8000 externally

---

## 10. TESTING & VALIDATION

### Manual Testing Checklist
- [ ] User can login with admin/admin123
- [ ] User can login with employee/employee123
- [ ] User can login with customer/customer123
- [ ] Admin redirects to `/admin` dashboard
- [ ] Employee redirects to `/employee` dashboard
- [ ] Customer redirects to `/main` dashboard
- [ ] Chat interface loads and WebSocket connects
- [ ] Voice recording captures audio
- [ ] ASR correctly transcribes speech
- [ ] LLM generates relevant responses
- [ ] TTS plays without reading emoji names
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
- **Cause**: GPU VRAM exhausted (KV cache + model)
- **Fix**: Reduce `n_ctx` to 2048, or use Q3_K_M quantization

**"FileNotFoundError: Vosk model not found"**
- **Cause**: Missing ASR model directory
- **Fix**: Download vosk-model-en-us-0.22-lgraph to `backend/Models/`

**"WebSocket connection failed"**
- **Cause**: RAG server not running or session invalid
- **Fix**: Check `python project_start_server.py` logs, ensure logged in

**"GPU not detected"**
- **Cause**: CUDA not installed or llama-cpp-python CPU build
- **Fix**: Reinstall llama-cpp-python with CMAKE_ARGS="-DLLAMA_CUDA=on"

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
**GGUF**: GPT-Generated Unified Format - quantized model file format  
**Q4_K_M**: 4-bit quantization with K-means, medium quality  
**CUDA**: Compute Unified Device Architecture - NVIDIA GPU programming  
**VRAM**: Video RAM - GPU memory  
**KV Cache**: Key-Value cache for attention mechanism in LLMs  
**CSRF**: Cross-Site Request Forgery - session security attack  
**PCM16**: Pulse Code Modulation, 16-bit - raw audio format  
**ChromaDB**: Embeddings database for vector similarity search  
**Vosk**: Offline speech recognition toolkit  
**FastAPI**: Modern Python web framework  
**WebSocket**: Full-duplex communication protocol  

---

## 15. CONTACT & SUPPORT

### Documentation References
- FastAPI: https://fastapi.tiangolo.com/
- llama.cpp: https://github.com/ggerganov/llama.cpp
- Vosk: https://alphacephei.com/vosk/
- ChromaDB: https://docs.trychroma.com/
- Qwen2.5: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct

### Project Structure Summary
```
Assistify Voice Help Desk
├── Authentication Layer (Login Server - Port 7001)
├── Voice Processing Layer (RAG Server - Port 7000)
├── AI Inference Layer (LLM Server - Port 8000)
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
