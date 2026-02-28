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
    # Load the Login_system.login_server module directly from file
    login_server = load_login_server_module()

    # Ensure the DB is located in the Login_system folder
    this_dir = os.path.dirname(__file__)
    db_path = os.path.join(this_dir, "users.db")
    login_server.DB_PATH = db_path

    # Initialize DB and tables (will create if missing)
    login_server.init_db()

    # Ensure credentials are set to simple values for development.
    # Delete any existing users with these usernames first so we can recreate them.
    conn = login_server.get_db()
    c = conn.cursor()
    for user, pwd, role in (("admin", "admin", "admin"), ("employee", "employee", "employee")):
        c.execute("DELETE FROM users WHERE username=?", (user,))
        conn.commit()
        login_server.create_user(user, pwd, role)
    conn.close()

    print(f"Seeded users into {db_path}")
    print("Credentials:\n - admin / admin\n - employee / employee")


if __name__ == "__main__":
    main()
