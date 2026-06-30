import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from Login_system.login_server import init_db, DB_PATH  # noqa: E402
from Login_system.dev_users import dev_user_summary  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Recreate users.db with bootstrap superadmin only.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Required to delete an existing users.db (destructive).",
    )
    args = parser.parse_args()

    db_path = Path(DB_PATH)
    if db_path.exists():
        if not args.force:
            print(
                f"[ERROR] {db_path} already exists. This script DELETES all users.",
                file=sys.stderr,
            )
            print(
                "  To recreate dev seed only: python Login_system/init_users_db.py --force",
                file=sys.stderr,
            )
            print(
                "  To restore a wiped account: python scripts/restore_ahmed_user.py",
                file=sys.stderr,
            )
            raise SystemExit(1)
        db_path.unlink()
        print(f"Deleted existing {db_path}")

    init_db()
    print(f"Created fresh {db_path} with users: {dev_user_summary()}")


if __name__ == "__main__":
    main()
