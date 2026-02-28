# Assistify Project Setup Requirements

## System Requirements

### Hardware
- **GPU**: NVIDIA GPU with CUDA support (RTX 3070 or similar)
- **VRAM**: Minimum 8GB GPU memory
- **RAM**: Minimum 16GB system RAM
- **Storage**: 20GB free space (for model files)

### Software
- **Operating System**: Windows 10/11
- **Python**: Version 3.10 or 3.11 (recommended: 3.11)
- **Conda**: Anaconda or Miniconda installed
- **Git**: Git for Windows (download from https://git-scm.com/download/win)

---

## Installation Steps

### Step 1: Install Git (if not installed)
1. Download Git from: https://git-scm.com/download/win
2. Run installer with default settings
3. Open Command Prompt and verify: `git --version`

### Step 2: Install Conda (if not installed)
1. Download Miniconda from: https://docs.conda.io/en/latest/miniconda.html
2. Install with default settings
3. Restart Command Prompt
4. Verify: `conda --version`

### Step 3: Clone the Repository
```bash
# Open Command Prompt or PowerShell
cd Desktop\AAST
git clone https://github.com/YOUR_USERNAME/assistify-rag-project.git
cd assistify-rag-project
```

### Step 4: Create Conda Environment
```bash
# Create environment named 'grad'
conda create -n grad python=3.11 -y

# Activate environment
conda activate grad
```

### Step 5: Install Python Dependencies
```bash
# Install PyTorch with CUDA support (for GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install all other dependencies
pip install -r requirements.txt
```

### Step 6: Install llama-cpp-python with CUDA
```powershell
# Important: Install with CUDA support for GPU acceleration
$env:CMAKE_ARGS="-DLLAMA_CUBLAS=ON"
pip install llama-cpp-python --force-reinstall --no-cache-dir
```

### Step 7: Download Model Files
**IMPORTANT**: Model files are too large for GitHub. Download separately:

1. **LLM Model (Qwen2.5-7B)**: 
   - Download from: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF
   - Files needed: `qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf` and `qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf`
   - Place in: `backend/Models/Qwen2.5-7B-LLM/`

2. **Whisper Model**: faster-whisper downloads automatically on first run
   - Default: `medium.en` model (will download ~1.5GB)
   - Location: `backend/Models/models--Systran--faster-whisper-medium.en/`

### Step 8: Setup Knowledge Base
```bash
# The sample knowledge base is included
# Location: sample_kb.txt
# You can add your own documents here
```

### Step 9: Configure Environment Variables
Create a `.env` file in project root:
```bash
SESSION_SECRET=your_64_byte_secret_here_change_this_in_production_minimum_length_required
GOOGLE_CLIENT_ID=your_google_client_id_optional
GOOGLE_CLIENT_SECRET=your_google_client_secret_optional
EMAILJS_PUBLIC_KEY=your_emailjs_public_key_optional
EMAILJS_PRIVATE_KEY=your_emailjs_private_key_optional
EMAILJS_SERVICE_ID=your_emailjs_service_id_optional
EMAILJS_TEMPLATE_ID=your_emailjs_template_id_optional
```

### Step 10: Start the System
```bash
# Easy method: Use the startup script
python scripts/project_start_server.py --production --quick --kill-ports

# Or start servers individually:
# Terminal 1: cd backend & python main_llm_server.py
# Terminal 2: cd backend & python assistify_rag_server.py  
# Terminal 3: cd Login_system & python login_server.py
```

### Step 11: Access the Application
Open browser and go to:
```
http://127.0.0.1:7001/login
```

Default credentials will need to be created on first registration.

---

## Common Issues & Solutions

### Issue 1: "CUDA not available"
**Solution**: 
- Reinstall PyTorch with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu118`
- Check GPU driver version: `nvidia-smi`
- Reinstall llama-cpp-python with CUDA flag (see Step 6)

### Issue 2: "Module not found" errors
**Solution**:
- Make sure conda environment is activated: `conda activate grad`
- Reinstall requirements: `pip install -r requirements.txt`

### Issue 3: "Port already in use"
**Solution**:
- Use the startup script with `--kill-ports` flag
- Or manually kill processes:
  ```powershell
  Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force
  Get-Process -Id (Get-NetTCPConnection -LocalPort 7000).OwningProcess | Stop-Process -Force
  Get-Process -Id (Get-NetTCPConnection -LocalPort 7001).OwningProcess | Stop-Process -Force
  ```

### Issue 4: Slow responses
**Solution**:
- Reduce `N_GPU_LAYERS` in config.py (try 8 instead of 10)
- Reduce `N_CTX` to 256
- Check GPU memory: `nvidia-smi`

### Issue 5: Model file not found
**Solution**:
- Download GGUF model files (both parts)
- Place in `backend/Models/Qwen2.5-7B-LLM/` folder
- Verify files exist before starting

### Issue 6: "llama-cpp-python" build errors
**Solution**:
- Make sure Visual Studio Build Tools installed
- Or download pre-built wheel from: https://github.com/abetlen/llama-cpp-python/releases

---

## Folder Structure
```
assistify-rag-project/
├── backend/
│   ├── main_llm_server.py
│   ├── assistify_rag_server.py
│   ├── knowledge_base.py
│   ├── database.py
│   ├── analytics.py
│   ├── toon.py
│   └── Models/               # You must add model files here
│       └── Qwen2.5-7B-LLM/
│           ├── qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
│           └── qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf
├── Login_system/
│   └── login_server.py
├── frontend/
│   └── index.html
├── scripts/
│   ├── project_start_server.py
│   └── start_all_servers.bat
├── docs/
│   └── (documentation files)
├── config.py
├── requirements.txt
├── .gitignore
├── .env                      # Create this file
└── README.md
```

---

## GPU Configuration

Edit `config.py` if needed:

```python
N_GPU_LAYERS = 10        # Number of layers on GPU (0-32)
                         # RTX 3070 8GB: Use 10
                         # RTX 4090 24GB: Use 32
                         # No GPU: Use 0

N_CTX = 512              # Context window size
N_BATCH = 2              # Batch size for processing
```

---

## Performance Expectations

**With RTX 3070 (10 GPU layers):**
- Startup time: ~45 seconds (all 3 servers)
- Greeting response: 3-4 seconds
- RAG query response: 10-15 seconds
- GPU memory usage: ~2.2GB during inference

**With CPU only (0 GPU layers):**
- Response time: 2-3x slower
- Not recommended for real-time voice

---

## Notes for Setup

1. **Before starting**: Install Git, Conda, and NVIDIA drivers
2. **Model files**: Must be downloaded separately (not in GitHub)
3. **Environment variables**: Optional for basic functionality
4. **First run**: Will take longer as models initialize
5. **Test with**: Simple "Hello" message first

---

## Support

If you encounter issues:
1. Check the error message in terminal
2. Verify conda environment is activated (`conda activate grad`)
3. Check if all 3 servers started (ports 8000, 7000, 7001)
4. Review "Common Issues" section above
5. Check GPU is detected: `nvidia-smi`

---

## Quick Verification Checklist

- [ ] Git installed and working
- [ ] Conda environment created and activated
- [ ] All requirements installed
- [ ] PyTorch with CUDA installed
- [ ] llama-cpp-python with CUDA built
- [ ] Model files downloaded and placed correctly
- [ ] Config.py settings reviewed
- [ ] All 3 servers started successfully
- [ ] Browser can access http://127.0.0.1:7001
- [ ] Can register and login
- [ ] Chat interface loads
- [ ] Can send test message and get response

**Once all checked: System is ready to use!**
