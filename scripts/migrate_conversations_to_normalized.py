#!/usr/bin/env python3
"""Migrate backend/conversations.json into normalized SQLite chat tables."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat_store import init_chat_store_schema, migrate_from_json  # noqa: E402

JSON_PATH = ROOT / "backend" / "conversations.json"


def main() -> int:
    init_chat_store_schema()
    count = migrate_from_json(JSON_PATH)
    print(f"Migrated {count} conversation(s) from {JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
