import sys
from app import app, db, bcrypt
from app.db_classes import User

def main():
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    password = input("Password: ").strip()
    if not password:
        print("Password cannot be empty.")
        sys.exit(1)

    is_admin = input("Admin? [y/N]: ").strip().lower() == "y"

    with app.app_context():
        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(username=username, password=hashed, admin=int(is_admin))
        db.session.add(user)
        db.session.commit()
        print(f"User '{username}' created (admin={is_admin}).")

if __name__ == "__main__":
    main()
