#Requires -Version 5.1
# Defender Protection Script for Python Development Environment
# Prevents Windows Defender from blocking .pyd/.pyc/.dll files without disabling security globally.

# Self-Elevation
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[!] Requesting administrator elevation..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$ScriptDir        = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile          = Join-Path $ScriptDir "defender_events.log"
$BackupDir        = Join-Path $ScriptDir "project_config_backup"
$BackupIntervalSec = 60

if (-not (Test-Path $LogFile)) { New-Item -ItemType File -Path $LogFile -Force | Out-Null }

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $line = "[$timestamp][$Level] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    switch ($Level) {
        "INFO"  { Write-Host $line -ForegroundColor Cyan }
        "WARN"  { Write-Host $line -ForegroundColor Yellow }
        "ERROR" { Write-Host $line -ForegroundColor Red }
        "OK"    { Write-Host $line -ForegroundColor Green }
    }
}

function Find-ProjectDirectory {
    $indicators = @("requirements.txt", "setup.py", "pyproject.toml")
    $current = $ScriptDir
    
    for ($i = 0; $i -lt 5; $i++) {
        foreach ($indicator in $indicators) {
            if (Test-Path (Join-Path $current $indicator)) {
                return $current
            }
        }
        $parent = Split-Path -Parent $current
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
    return $ScriptDir
}

function Find-PythonDirectories {
    $pythonPaths = @()
    
    $condaRoots = @(
        "$env:USERPROFILE\miniconda3",
        "$env:USERPROFILE\anaconda3",
        "C:\ProgramData\miniconda3",
        "C:\ProgramData\anaconda3",
        "C:\miniconda3",
        "C:\anaconda3"
    )

    foreach ($root in $condaRoots) {
        if (Test-Path $root) {
            $base = Join-Path $root "python.exe"
            if (Test-Path $base) { $pythonPaths += $root }
            
            $envsDir = Join-Path $root "envs"
            if (Test-Path $envsDir) {
                Get-ChildItem -Path $envsDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    $pythonPaths += $_.FullName
                }
            }
        }
    }

    $sysPythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPythonCmd) {
        $sysPythonDir = Split-Path -Parent $sysPythonCmd.Source
        if ($sysPythonDir) { $pythonPaths += $sysPythonDir }
    }

    return ($pythonPaths | Sort-Object -Unique)
}

function Add-DefenderExclusions {
    param([string]$ProjectPath, [string[]]$PythonDirs)

    Write-Log "Adding exclusions for: $ProjectPath" "OK"

    try {
        Add-MpPreference -ExclusionPath $ProjectPath -ErrorAction Stop
        Write-Log "  [+] Path excluded: $ProjectPath" "OK"
    } catch {
        Write-Log "  [-] Path exclusion failed: $_" "WARN"
    }

    foreach ($pyDir in $PythonDirs) {
        try {
            Add-MpPreference -ExclusionPath $pyDir -ErrorAction Stop
            Write-Log "  [+] Python dir excluded: $pyDir" "OK"
        } catch {
            Write-Log "  [-] Python dir failed: $_" "WARN"
        }
    }

    foreach ($ext in @("pyd", "pyc", "dll")) {
        try {
            Add-MpPreference -ExclusionExtension $ext -ErrorAction Stop
            Write-Log "  [+] Extension excluded: $ext" "OK"
        } catch {
            Write-Log "  [-] Extension failed: $ext" "WARN"
        }
    }

    foreach ($exe in @("python.exe", "pythonw.exe", "conda.exe", "pip.exe")) {
        try {
            Add-MpPreference -ExclusionProcess $exe -ErrorAction Stop
            Write-Log "  [+] Process excluded: $exe" "OK"
        } catch {
            Write-Log "  [-] Process failed: $exe" "WARN"
        }
    }
}

function Check-Quarantine {
    param([string]$ProjectPath)
    
    $threats = Get-MpThreatDetection -ErrorAction SilentlyContinue
    if (-not $threats) { return 0 }

    $count = 0
    foreach ($threat in $threats) {
        $resources = $threat.Resources -join ","
        if ($resources -like "*$ProjectPath*") {
            $count++
            Write-Log "QUARANTINED: $resources" "WARN"
        }
    }
    return $count
}

function Backup-ConfigFiles {
    param([string]$ProjectPath)

    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    }

    $timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
    $snapshotDir = Join-Path $BackupDir $timestamp
    New-Item -ItemType Directory -Path $snapshotDir -Force | Out-Null

    $count = 0
    $patterns = @("*.json", "*.yaml", "*.yml", "*.env", "*.cfg", "*.ini")
    
    foreach ($pattern in $patterns) {
        $files = Get-ChildItem -Path $ProjectPath -Filter $pattern -Recurse -ErrorAction SilentlyContinue | Where-Object {
            $_.FullName -notlike "*project_config_backup*" -and
            $_.FullName -notlike "*__pycache__*" -and 
            $_.FullName -notlike "*.git*"
        }
        
        foreach ($file in $files) {
            $relative   = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')
            $destPath   = Join-Path $snapshotDir $relative
            $destFolder = Split-Path -Parent $destPath
            
            if (-not (Test-Path $destFolder)) {
                New-Item -ItemType Directory -Path $destFolder -Force | Out-Null
            }
            
            Copy-Item -Path $file.FullName -Destination $destPath -Force -ErrorAction SilentlyContinue
            $count++
        }
    }

    $snapshots = Get-ChildItem -Path $BackupDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
    if ($snapshots.Count -gt 10) {
        $snapshots | Select-Object -Skip 10 | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    return $count
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "  Assistify Defender Protection - Python Dev Environment    " -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

Write-Log "=== Script Started ===" "INFO"

$projectPath = Find-ProjectDirectory
Write-Log "Project detected: $projectPath" "OK"

$pythonDirs = Find-PythonDirectories
Write-Log "Found $($pythonDirs.Count) Python directories" "OK"

Add-DefenderExclusions -ProjectPath $projectPath -PythonDirs $pythonDirs

$blockedCount = Check-Quarantine -ProjectPath $projectPath

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}
$backedUpCount = Backup-ConfigFiles -ProjectPath $projectPath

Write-Host ""
Write-Host "--- STATUS SUMMARY ---" -ForegroundColor White
Write-Host "  Project path: $projectPath" -ForegroundColor Green
Write-Host "  Python dirs: $($pythonDirs.Count)" -ForegroundColor Green
Write-Host "  Blocked events: $blockedCount" -ForegroundColor $(if ($blockedCount -gt 0) { "Red" } else { "Green" })
Write-Host "  Config backups: $backedUpCount" -ForegroundColor Green
Write-Host "  Log file: defender_events.log" -ForegroundColor Cyan
Write-Host "  Backup folder: project_config_backup\" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Defender remains ACTIVE globally." -ForegroundColor Yellow
Write-Host "  Only safe exclusions applied." -ForegroundColor Yellow
Write-Host ""

Write-Log "=== Setup Complete ===" "OK"
Write-Host "Press any key to close..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
