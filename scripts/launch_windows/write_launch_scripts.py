#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Windows batch launchers for split-terminal mode."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ollama_bootstrap import resolve_ollama_exe  # noqa: E402

LAUNCH_DIR = Path(__file__).resolve().parent

_ENV_KEYS = (
    "LLM_SERVER_URL",
    "LLM_SERVER_PORT",
    "OLLAMA_MODEL",
    "OLLAMA_CLI",
    "OLLAMA_KEEP_ALIVE",
    "PIPER_EN_VOICE_PATH",
    "PIPER_AR_VOICE_PATH",
    "WHISPER_DEVICE",
    "WHISPER_COMPUTE_TYPE",
    "RAG_USE_GPU",
    "USE_WHISPER",
    "WHISPER_MODEL",
    "WHISPER_CHUNK_MS",
)


def _bat_set(key: str, value: str) -> str:
    escaped = str(value).replace('"', "")
    return f'set "{key}={escaped}"'


def write_env_bat(repo_root: Path, python_exe: str, extra: dict | None = None) -> Path:
    try:
        from dotenv import load_dotenv

        load_dotenv(repo_root / ".env")
    except Exception:
        pass

    lines = [
        "@echo off",
        _bat_set("REPO_ROOT", str(repo_root)),
        _bat_set("PYTHON_EXE", python_exe),
        _bat_set("PYTHONPATH", str(repo_root)),
        _bat_set("KMP_DUPLICATE_LIB_OK", "TRUE"),
        _bat_set("CUDA_VISIBLE_DEVICES", os.environ.get("CUDA_VISIBLE_DEVICES", "0")),
        _bat_set("OLLAMA_KEEP_ALIVE", os.environ.get("OLLAMA_KEEP_ALIVE", "5m")),
        _bat_set("OLLAMA_EXE", resolve_ollama_exe()),
    ]
    for key in _ENV_KEYS:
        val = os.environ.get(key)
        if val:
            lines.append(_bat_set(key, val))
    if extra:
        for key, val in extra.items():
            if val is not None:
                lines.append(_bat_set(key, val))

    path = LAUNCH_DIR / "_env.bat"
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def _bat_header(window_title: str) -> list[str]:
    return [
        "@echo off",
        f"title {window_title}",
        'call "%~dp0_env.bat"',
        'cd /d "%REPO_ROOT%"',
    ]


def _uvicorn_bat_lines(
    module: str,
    host: str,
    port: int,
    log_level: str,
    keep_alive: int,
    reload_flag: bool,
) -> list[str]:
    lines = [
        '"%PYTHON_EXE%" -u -m uvicorn',
        module,
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        log_level,
        "--timeout-keep-alive",
        str(keep_alive),
    ]
    if reload_flag:
        lines.append("--reload")
    return lines


def _maybe_log_wrap(
    repo_root: Path,
    python_exe: str,
    log_name: str,
    capture_logs: bool,
    inner_cmd: str,
) -> str:
    if not capture_logs:
        return inner_cmd
    log_file = repo_root / "logs" / f"{log_name}.log"
    wrapper = repo_root / "scripts" / "run_with_log.py"
    return f'"{python_exe}" -u "{wrapper}" "{log_file}" {inner_cmd}'


def write_service_bats(
    repo_root: Path,
    python_exe: str,
    *,
    llm: dict,
    rag: dict,
    login: dict,
    rag_env: dict,
    piper_env: dict,
    reload_flag: bool,
    capture_logs: bool = False,
) -> dict[str, Path]:
    write_env_bat(repo_root, python_exe, {**piper_env, **rag_env})

    if capture_logs:
        (repo_root / "logs").mkdir(parents=True, exist_ok=True)

    bats: dict[str, Path] = {}

    ollama_path = LAUNCH_DIR / "run_ollama.bat"
    ollama_path.write_text(
        "\r\n".join(
            _bat_header("Assistify Ollama")
            + [
                "echo Ollama binary: %OLLAMA_EXE%",
                "powershell -NoProfile -Command \"if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 11434 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }\" >nul 2>&1",
                "if not errorlevel 1 goto :already_running",
                'if exist "%OLLAMA_EXE%" goto :run_ollama',
                'where ollama >nul 2>&1',
                "if not errorlevel 1 (",
                "  set \"OLLAMA_EXE=ollama\"",
                "  goto :run_ollama",
                ")",
                'echo [ERROR] Ollama not found at "%OLLAMA_EXE%"',
                "echo Install from https://ollama.com/download or open the Ollama tray app",
                "echo Re-run launcher with --no-ollama if Ollama is already managed externally",
                "pause",
                "exit /b 1",
                ":already_running",
                "echo [OLLAMA] Already running on port 11434",
                "echo.",
                "echo Installed models:",
                'if exist "%OLLAMA_EXE%" ("%OLLAMA_EXE%" list) else (ollama list)',
                "echo.",
                "echo Do NOT run 'ollama serve' while port 11434 is in use.",
                "echo For a clean restart: python start_main_servers.py --restart-ollama",
                "echo.",
                "echo Monitor window — safe to close; does not stop tray Ollama.",
                "cmd /k",
                ":run_ollama",
                "echo Starting Ollama on port 11434...",
                _maybe_log_wrap(
                    repo_root,
                    python_exe,
                    "ollama",
                    capture_logs,
                    '"%OLLAMA_EXE%" serve',
                ),
                "if errorlevel 1 (",
                "  echo.",
                "  echo [ERROR] ollama serve failed — port 11434 may already be in use.",
                "  echo Quit Ollama from the system tray, then run:",
                "  echo   python start_main_servers.py --restart-ollama",
                ")",
                "pause",
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    bats["Ollama"] = ollama_path

    piper_cmd = _maybe_log_wrap(
        repo_root,
        python_exe,
        "piper",
        capture_logs,
        " ".join(
            _uvicorn_bat_lines(
                "tts_service.piper_server:app",
                "127.0.0.1",
                5002,
                "info",
                300,
                reload_flag,
            )
        ),
    )
    piper_path = LAUNCH_DIR / "run_piper.bat"
    piper_path.write_text(
        "\r\n".join(
            _bat_header("Assistify Piper")
            + [
                "echo Starting Piper TTS on port 5002...",
                piper_cmd,
                "pause",
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    bats["Piper"] = piper_path

    for key, svc, path_name, log_name in (
        ("LLM", llm, "run_llm.bat", "llm"),
        ("RAG", rag, "run_rag.bat", "rag"),
        ("Login", login, "run_login.bat", "login"),
    ):
        uvicorn_parts = _uvicorn_bat_lines(
            svc["module"],
            svc["host"],
            svc["port"],
            svc["log_level"],
            svc["keep_alive"],
            reload_flag,
        )
        cmd = _maybe_log_wrap(
            repo_root,
            python_exe,
            log_name,
            capture_logs,
            " ".join(uvicorn_parts),
        )
        bat_path = LAUNCH_DIR / path_name
        bat_path.write_text(
            "\r\n".join(
                _bat_header(f"Assistify {key}")
                + [
                    f"echo Starting {key} on port {svc['port']}...",
                    cmd,
                    "pause",
                ]
            )
            + "\r\n",
            encoding="utf-8",
        )
        bats[key] = bat_path

    return bats
