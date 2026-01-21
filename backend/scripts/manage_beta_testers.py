#!/usr/bin/env python3
"""
Manage beta tester access for ScholarHub.

Usage:
    # Add a beta tester
    docker-compose exec backend python scripts/manage_beta_testers.py add user@example.com

    # Remove beta access (revert to free)
    docker-compose exec backend python scripts/manage_beta_testers.py remove user@example.com

    # List all beta testers
    docker-compose exec backend python scripts/manage_beta_testers.py list
"""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings


def get_db_connection():
    engine = create_engine(settings.DATABASE_URL)
    return engine.connect()


def add_beta_tester(email: str):
    """Upgrade a user to beta tester tier."""
    conn = get_db_connection()

    # Check if user exists
    result = conn.execute(
        text("SELECT id, email FROM users WHERE email = :email"),
        {"email": email}
    )
    user = result.fetchone()

    if not user:
        print(f"Error: User with email '{email}' not found.")
        conn.close()
        return False

    # Update their subscription to beta
    conn.execute(
        text("""
            UPDATE user_subscriptions
            SET tier_id = 'beta', updated_at = NOW()
            WHERE user_id = :user_id
        """),
        {"user_id": user[0]}
    )
    conn.commit()
    conn.close()

    print(f"Successfully upgraded '{email}' to Beta Tester tier.")
    return True


def remove_beta_tester(email: str):
    """Revert a user back to free tier."""
    conn = get_db_connection()

    # Check if user exists
    result = conn.execute(
        text("SELECT id, email FROM users WHERE email = :email"),
        {"email": email}
    )
    user = result.fetchone()

    if not user:
        print(f"Error: User with email '{email}' not found.")
        conn.close()
        return False

    # Update their subscription to free
    conn.execute(
        text("""
            UPDATE user_subscriptions
            SET tier_id = 'free', updated_at = NOW()
            WHERE user_id = :user_id
        """),
        {"user_id": user[0]}
    )
    conn.commit()
    conn.close()

    print(f"Successfully reverted '{email}' to Free tier.")
    return True


def list_beta_testers():
    """List all users with beta tester access."""
    conn = get_db_connection()

    result = conn.execute(
        text("""
            SELECT u.email, u.first_name, u.last_name, us.created_at
            FROM users u
            JOIN user_subscriptions us ON u.id = us.user_id
            WHERE us.tier_id = 'beta'
            ORDER BY us.created_at DESC
        """)
    )

    testers = result.fetchall()
    conn.close()

    if not testers:
        print("No beta testers found.")
        return

    print(f"\nBeta Testers ({len(testers)}):")
    print("-" * 60)
    for tester in testers:
        name = f"{tester[1] or ''} {tester[2] or ''}".strip() or "No name"
        print(f"  {tester[0]:40} ({name})")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "add":
        if len(sys.argv) < 3:
            print("Error: Please provide an email address.")
            print("Usage: python manage_beta_testers.py add user@example.com")
            sys.exit(1)
        add_beta_tester(sys.argv[2])

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Error: Please provide an email address.")
            print("Usage: python manage_beta_testers.py remove user@example.com")
            sys.exit(1)
        remove_beta_tester(sys.argv[2])

    elif command == "list":
        list_beta_testers()

    else:
        print(f"Unknown command: {command}")
        print("Available commands: add, remove, list")
        sys.exit(1)


if __name__ == "__main__":
    main()
