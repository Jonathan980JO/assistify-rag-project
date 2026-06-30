#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror a child process stdout/stderr to the console and a log file."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: run_with_log.py <log-file> <command> [args...]", file=sys.stderr)
        return 2

    log_path = Path(sys.argv[1])
    cmd = sys.argv[2:]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"\n--- session start ---\n")
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log_file.write(line)
            log_file.flush()
        return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
