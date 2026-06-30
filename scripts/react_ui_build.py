#!/usr/bin/env python3
"""Build assistify-ui-design React static export for Login server /frontend/."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REACT_DIR = REPO_ROOT / "assistify-ui-design"
OUT_INDEX = REACT_DIR / "out" / "index.html"
OUT_NEXT = REACT_DIR / "out" / "_next"
NODE_MODULES = REACT_DIR / "node_modules"
PACKAGE_LOCK_MARKER = NODE_MODULES / ".package-lock.json"


def find_npm() -> str | None:
    for name in ("npm", "npm.cmd"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _needs_npm_install(*, force_install: bool = False) -> bool:
    if force_install or not NODE_MODULES.is_dir():
        return True
    pkg_json = REACT_DIR / "package.json"
    pkg_lock = REACT_DIR / "package-lock.json"
    if not pkg_lock.is_file():
        return False
    try:
        marker_mtime = PACKAGE_LOCK_MARKER.stat().st_mtime if PACKAGE_LOCK_MARKER.is_file() else 0
        lock_mtime = pkg_lock.stat().st_mtime
        json_mtime = pkg_json.stat().st_mtime if pkg_json.is_file() else 0
        return lock_mtime > marker_mtime or json_mtime > marker_mtime
    except OSError:
        return True


def _artifacts_ok() -> bool:
    return OUT_INDEX.is_file() and OUT_NEXT.is_dir()


def _run_npm(npm: str, args: list[str]) -> int:
    prefix = "[UI]"
    print(f"{prefix} Running: npm {' '.join(args)} (cwd={REACT_DIR})")
    proc = subprocess.Popen(
        [npm, *args],
        cwd=str(REACT_DIR),
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"{prefix} {line.rstrip()}")
    return proc.wait()


def ensure_react_ui_built(*, skip: bool = False, force_install: bool = False) -> bool:
    """Run npm install (when needed) + npm run build. Returns False on critical failure."""
    if skip:
        if _artifacts_ok():
            print("[UI] Skipping build (--skip-ui-build); using existing out/")
            return True
        print("[UI] ERROR: --skip-ui-build but assistify-ui-design/out/ is missing or incomplete.")
        print("[UI] Run: cd assistify-ui-design && npm install && npm run build")
        return False

    npm = find_npm()
    if npm is None:
        if _artifacts_ok():
            print("[UI] WARN: npm not found on PATH; using existing out/ (install Node.js to rebuild)")
            return True
        print("[UI] ERROR: npm not found and no React build at assistify-ui-design/out/")
        print("[UI] Install Node.js (https://nodejs.org/), then: cd assistify-ui-design && npm install && npm run build")
        return False

    if not REACT_DIR.is_dir():
        print(f"[UI] ERROR: React project not found at {REACT_DIR}")
        return False

    if _needs_npm_install(force_install=force_install):
        if _run_npm(npm, ["install"]) != 0:
            if _artifacts_ok():
                print("[UI] WARN: npm install failed; continuing with stale out/")
                return True
            return False
    else:
        print("[UI] node_modules up to date — skipping npm install")

    if _run_npm(npm, ["run", "build"]) != 0:
        if _artifacts_ok():
            print("[UI] WARN: npm run build failed; continuing with stale out/")
            return True
        print("[UI] ERROR: npm run build failed and no existing out/ to fall back on.")
        return False

    if not _artifacts_ok():
        print("[UI] ERROR: build finished but out/index.html or out/_next/ is missing.")
        return False

    print(f"[UI] React UI ready at {OUT_INDEX}")
    return True


def main() -> int:
    skip = "--skip-ui-build" in sys.argv
    force = "--force-install" in sys.argv
    return 0 if ensure_react_ui_built(skip=skip, force_install=force) else 1


if __name__ == "__main__":
    raise SystemExit(main())
