"""Provision a synthetic-only operator from a trusted local terminal."""

import argparse
from getpass import getpass
from os import environ
from re import fullmatch

from sqlalchemy import text

from .database import database_engine
from .passwords import hash_password

ROLES = ("administrator", "osint_analyst", "forensic_examiner", "supervisor")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("role", choices=ROLES, nargs="+")
    args = parser.parse_args()
    if not fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", args.username):
        parser.error("Invalid username.")
    raw_url = environ.get("MARGONO_DATABASE_URL")
    if not raw_url or environ.get("MARGONO_MODE", "simulation") != "simulation":
        parser.error("Configure the local simulation database first.")

    password = getpass("New local password: ")
    if not 12 <= len(password) <= 256 or password != getpass("Confirm password: "):
        parser.error("Use 12–256 characters and enter the same password twice.")

    with database_engine(raw_url).begin() as db:
        user_id = db.scalar(
            text("""INSERT INTO users (username, password_hash) VALUES (:username, :password)
                    ON CONFLICT (username) DO NOTHING RETURNING id"""),
            {"username": args.username, "password": hash_password(password)},
        )
        if user_id is None:
            parser.error("Username already exists.")
        db.execute(
            text("INSERT INTO user_roles (user_id, role_slug) VALUES (:user, :role)"),
            [{"user": user_id, "role": role} for role in set(args.role)],
        )
    print("Local operator created.")


if __name__ == "__main__":
    main()
