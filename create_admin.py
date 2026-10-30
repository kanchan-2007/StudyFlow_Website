import os
import sqlite3
import getpass
import re

from werkzeug.security import generate_password_hash

try:
    import app as studyflow
except Exception as exc:
    print("Could not import app.py:", exc)
    raise SystemExit(1)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = getattr(
    studyflow,
    "DB_PATH",
    os.path.join(BASE_DIR, "study_planner.db")
)

if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(BASE_DIR, DB_PATH)


def main():
    print("\n=== StudyFlow Admin Account Setup ===\n")

    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password (minimum 8 characters): ")
    confirm = getpass.getpass("Confirm password: ")

    if not name:
        print("ERROR: Name is required.")
        return

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("ERROR: Enter a valid email address.")
        return

    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        return

    if password != confirm:
        print("ERROR: Passwords do not match.")
        return

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found: {DB_PATH}")
        print("Run app.py once first to initialize the database.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA busy_timeout = 5000")

        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        if "users" not in tables:
            print("ERROR: 'users' table was not found in the database.")
            print("Check that DB_PATH points to your existing StudyFlow database.")
            return

        info = conn.execute("PRAGMA table_info(users)").fetchall()
        columns = {row["name"] for row in info}

        def choose(*names):
            return next((n for n in names if n in columns), None)

        name_col = choose("name", "full_name", "username")
        email_col = choose("email")
        password_col = choose("password_hash", "password")
        role_col = choose("role")
        verified_col = choose(
            "verified", "is_verified", "email_verified"
        )
        active_col = choose("is_active", "active", "enabled")

        required = {
            "name": name_col,
            "email": email_col,
            "password": password_col,
            "role": role_col,
        }

        missing = [key for key, value in required.items() if value is None]

        if missing:
            print("ERROR: Could not identify these user fields:", ", ".join(missing))
            print("Actual users table columns:", ", ".join(sorted(columns)))
            print("No database changes were made.")
            return

        existing = conn.execute(
            f'SELECT * FROM users WHERE "{email_col}" = ?',
            (email,)
        ).fetchone()

        values = {
            name_col: name,
            email_col: email,
            password_col: generate_password_hash(password),
            role_col: "admin",
        }

        if verified_col:
            values[verified_col] = 1

        if active_col:
            values[active_col] = 1

        if existing:
            user_id_col = choose("id", "user_id")
            existing_id = existing[user_id_col] if user_id_col else None

            if existing_id is not None:
                conn.execute(
                    f'UPDATE users SET {", ".join("[" + c + "] = ?" for c in values if c != email_col)} '
                    f'WHERE "{user_id_col}" = ?',
                    tuple(v for c, v in values.items() if c != email_col)
                    + (existing_id,)
                )
            else:
                print("ERROR: Existing account ID could not be identified.")
                return

            print("\nExisting account updated to admin.")
        else:
            for row in info:
                col = row["name"]
                not_null = row["notnull"]
                default = row["dflt_value"]
                primary_key = row["pk"]

                if (
                    not_null
                    and default is None
                    and not primary_key
                    and col not in values
                ):
                    print(
                        f"ERROR: Required database field '{col}' "
                        "needs an app-specific value."
                    )
                    print("No account was created.")
                    return

            fields = list(values)
            placeholders = ", ".join("?" for _ in fields)

            conn.execute(
                f'INSERT INTO users ({", ".join(chr(34) + c + chr(34) for c in fields)}) '
                f'VALUES ({placeholders})',
                tuple(values[c] for c in fields)
            )

            print("\nAdmin account created successfully.")

        conn.commit()

        print("Email verification: enabled, if supported by the schema.")
        print("Admin email:", email)
        print("Login page: http://127.0.0.1:5000/login")
        print("Admin dashboard: http://127.0.0.1:5000/admin")

    except sqlite3.Error as exc:
        conn.rollback()
        print("DATABASE ERROR:", exc)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
