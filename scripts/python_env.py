#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolve which Python executable should run Assistify services."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CONDA_ENV_NAME = "assistify_main"


def _project_venv_python(repo_root: Path) -> Path | None:
    is_windows = os.name == "nt"
    name = "python.exe" if is_windows else "python"
    sub = "Scripts" if is_windows else "bin"
    candidate = repo_root / ".venv" / sub / name
    return candidate if candidate.exists() else None


def _conda_python(repo_root: Path) -> Path | None:
    is_windows = os.name == "nt"
    name = "python.exe" if is_windows else "python"
    roots: list[Path] = []
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    for base_name in ("miniconda3", "anaconda3", "Miniconda3", "Anaconda3"):
        roots.append(user_profile / base_name)
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        for base_name in ("miniconda3", "anaconda3", "Miniconda3", "Anaconda3"):
            roots.append(Path(program_data) / base_name)
    for key in ("CONDA_PREFIX", "CONDA_ROOT", "_CONDA_ROOT"):
        val = os.environ.get(key)
        if val:
            p = Path(val)
            roots.append(p)
            roots.append(p.parent.parent)
    seen: set[Path] = set()
    for base in roots:
        if base in seen:
            continue
        seen.add(base)
        if is_windows:
            candidate = base / "envs" / CONDA_ENV_NAME / name
        else:
            candidate = base / "envs" / CONDA_ENV_NAME / "bin" / name
        if candidate.exists():
            return candidate
    return None


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _venv_has_core_deps(python_exe: Path) -> bool:
    """True when the interpreter can import packages required by all services."""
    try:
        proc = subprocess.run(
            [str(python_exe), "-c", "import fastapi, uvicorn"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def resolve_project_python(repo_root: Path) -> Path:
    """Pick Python for launcher + service windows.

    Priority:
    1. Active project ``.venv`` only if it has core deps (fastapi/uvicorn)
    2. Conda env ``assistify_main``
    3. Project ``.venv`` on disk if usable
    4. Current interpreter
    """
    repo_root = repo_root.resolve()
    venv_dir = repo_root / ".venv"
    venv_python = _project_venv_python(repo_root)

    def _usable_venv() -> Path | None:
        if venv_python is None:
            return None
        if _venv_has_core_deps(venv_python):
            return venv_python
        return None

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env and venv_python:
        if Path(virtual_env).resolve() == venv_dir.resolve():
            ok = _usable_venv()
            if ok is not None:
                return ok

    running = Path(sys.executable)
    if venv_python and _is_under(running, venv_dir):
        ok = _usable_venv()
        if ok is not None:
            return ok

    conda = _conda_python(repo_root)
    if conda is not None:
        return conda

    ok = _usable_venv()
    if ok is not None:
        return ok

    return running


def active_venv_missing_deps(repo_root: Path) -> bool:
    """True when the shell is in project .venv but it cannot run the stack."""
    repo_root = repo_root.resolve()
    venv_python = _project_venv_python(repo_root)
    if venv_python is None:
        return False
    venv_dir = repo_root / ".venv"
    virtual_env = os.environ.get("VIRTUAL_ENV")
    in_venv = bool(
        virtual_env and Path(virtual_env).resolve() == venv_dir.resolve()
    ) or _is_under(Path(sys.executable), venv_dir)
    return in_venv and not _venv_has_core_deps(venv_python)


def python_env_label(python_exe: Path) -> str:
    normalized = str(python_exe).replace("\\", "/")
    if "/.venv/" in normalized:
        return ".venv"
    if f"/envs/{CONDA_ENV_NAME}/" in normalized:
        return f"conda:{CONDA_ENV_NAME}"
    return "system"
