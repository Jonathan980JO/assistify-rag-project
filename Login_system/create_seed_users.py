import os
import importlib.util


def load_login_server_module():
    this_dir = os.path.dirname(__file__)
    login_server_path = os.path.join(this_dir, "login_server.py")
    spec = importlib.util.spec_from_file_location("login_server", login_server_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    login_server = load_login_server_module()

    this_dir = os.path.dirname(__file__)
    db_path = os.path.join(this_dir, "users.db")
    login_server.DB_PATH = db_path

    login_server.init_db()

    conn = login_server.get_db()
    c = conn.cursor()
    try:
        from Login_system.dev_users import remove_legacy_demo_users, seed_dev_users
    except ImportError:
        from dev_users import remove_legacy_demo_users, seed_dev_users

    removed = remove_legacy_demo_users(c)
    seed_dev_users(c, login_server.pwd_context, tenant_id=login_server.DEFAULT_TENANT_ID)
    conn.commit()
    conn.close()

    print(f"Seeded bootstrap account into {db_path}")
    print("Credentials:\n - superadmin / superadmin")
    if removed:
        print(f"Removed legacy demo accounts: {', '.join(removed)}")


if __name__ == "__main__":
    main()
