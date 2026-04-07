# Run this script as Administrator (right-click PowerShell -> Run as Administrator)
# It helps download/verify CUDA and then builds a CUDA-enabled llama-cpp-python wheel.
# IMPORTANT: I cannot perform system installs for you. Run this file yourself as Admin.

function Abort($msg){ Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# 1) Ensure running as admin
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Abort "Please re-run this script from an elevated (Administrator) PowerShell."
}

Write-Host "1/5: Opening NVIDIA CUDA Downloads page in your browser..." -ForegroundColor Cyan
Start-Process "https://developer.nvidia.com/cuda-downloads"
Write-Host "Please download and install the CUDA Toolkit matching your driver (CUDA 13.x recommended).
After installation and reboot, return here and press Enter to continue." -ForegroundColor Yellow
Read-Host -Prompt "Press Enter after CUDA is installed and you've rebooted"

# 2) Try to locate nvcc
Write-Host "2/5: Locating nvcc..." -ForegroundColor Cyan
$nvcc = Get-Command nvcc -ErrorAction SilentlyContinue
if (-not $nvcc) {
    # search common install folder
    $found = Get-ChildItem 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA' -Recurse -Filter nvcc.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $nvccPath = $found.DirectoryName
        Write-Host "Found nvcc at $($found.FullName). Adding to PATH for this session." -ForegroundColor Green
        $env:Path = "$nvccPath;$env:Path"
    } else {
        Abort "Could not find nvcc on PATH. Ensure CUDA Toolkit installed and nvcc available."
    }
} else {
    Write-Host "nvcc found: $($nvcc.Path)" -ForegroundColor Green
}

# show versions
Write-Host "nvcc --version output:" -ForegroundColor Cyan
try { nvcc --version } catch { Write-Host "(nvcc command failed)" -ForegroundColor Yellow }
Write-Host "nvidia-smi output:" -ForegroundColor Cyan
try { nvidia-smi } catch { Write-Host "(nvidia-smi failed)" -ForegroundColor Yellow }

Read-Host -Prompt "If nvcc and nvidia-smi look OK, press Enter to continue (otherwise abort with Ctrl+C)"

# 3) Prepare environment: set short TEMP, run vcvars64 if available, upgrade pip and pre-install binary wheels
Write-Host "3/5: Preparing build environment (short TEMP, VS vars, pip upgrade, pre-install numpy/cython)" -ForegroundColor Cyan
# Use a short temp path to avoid long-path linker issues
$shortTemp = 'C:\tmp_pip_build'
if (-not (Test-Path $shortTemp)) { New-Item -ItemType Directory -Path $shortTemp | Out-Null }
$env:TEMP = $shortTemp
$env:TMP = $shortTemp

# Try to source Visual Studio vcvars64 if present to ensure cl/link are configured
$vsVars = Get-ChildItem 'C:\Program Files\Microsoft Visual Studio' -Recurse -Filter vcvars64.bat -ErrorAction SilentlyContinue | Select-Object -First 1
if ($vsVars) {
    Write-Host "Sourcing Visual Studio environment: $($vsVars.FullName)" -ForegroundColor Green
    & "$($vsVars.FullName)"
} else {
    Write-Host "vcvars64.bat not found automatically; ensure Visual Studio 'Desktop development with C++' is installed." -ForegroundColor Yellow
}

python -m pip install -U pip setuptools wheel cmake scikit-build
if ($LASTEXITCODE -ne 0) { Write-Host "Warning: pip upgrade may have warnings; continuing." -ForegroundColor Yellow }

# Pre-install binary wheels that avoid building from source on Windows
Write-Host "Installing binary wheels: numpy, Cython" -ForegroundColor Cyan
python -m pip install --upgrade --prefer-binary numpy Cython
if ($LASTEXITCODE -ne 0) { Write-Host "Warning: pre-install of numpy/Cython failed; build may still attempt to compile them." -ForegroundColor Yellow }

# 4) Build and install llama-cpp-python with CUBLAS enabled
Write-Host "4/5: Building and installing CUDA-enabled llama-cpp-python (this will take several minutes)" -ForegroundColor Cyan
$env:LLAMA_CUBLAS='1'
python -m pip install --force-reinstall --no-cache-dir --no-binary :all: llama-cpp-python
if ($LASTEXITCODE -ne 0) {
    Abort "Failed to build/install llama-cpp-python. Inspect the console for errors."
}

# 5) Start the project servers (quick mode) using the current Python
Write-Host "5/5: Starting the project servers (production quick mode)" -ForegroundColor Cyan
Write-Host "This will kill ports and spawn uvicorn processes; check the 'logs' folder for output." -ForegroundColor Yellow
python scripts/project_start_server.py --production --quick --kill-ports

Write-Host "Done. If servers failed to start, check logs/llm.log and logs/rag.log for errors." -ForegroundColor Green
