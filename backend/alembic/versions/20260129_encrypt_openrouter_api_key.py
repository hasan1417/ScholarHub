"""Encrypt stored OpenRouter API keys

Revision ID: 20260129_encrypt_openrouter_api_key
Revises: 9f7386efdf23
Create Date: 2026-01-29 00:00:00.000000

"""
from typing import Sequence, Union
import os

from alembic import op
import sqlalchemy as sa
from cryptography.fernet import Fernet

# revision identifiers, used by Alembic.
revision: str = "20260129_encrypt_openrouter_api_key"
down_revision: Union[str, None] = "9f7386efdf23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENCRYPTION_PREFIX = "enc:v1:"


def _get_fernet() -> Fernet:
    key = os.getenv("OPENROUTER_KEY_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_KEY_ENCRYPTION_KEY must be set to run this migration")
    return Fernet(key)


def upgrade() -> None:
    conn = op.get_bind()
    fernet = _get_fernet()

    rows = conn.execute(
        sa.text("SELECT id, openrouter_api_key FROM users WHERE openrouter_api_key IS NOT NULL")
    ).fetchall()

    for row in rows:
        raw_value = row.openrouter_api_key
        if not raw_value or raw_value.startswith(ENCRYPTION_PREFIX):
            continue
        encrypted = fernet.encrypt(raw_value.encode("utf-8")).decode("utf-8")
        new_value = f"{ENCRYPTION_PREFIX}{encrypted}"
        conn.execute(
            sa.text("UPDATE users SET openrouter_api_key = :val WHERE id = :id"),
            {"val": new_value, "id": row.id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    fernet = _get_fernet()

    rows = conn.execute(
        sa.text("SELECT id, openrouter_api_key FROM users WHERE openrouter_api_key IS NOT NULL")
    ).fetchall()

    for row in rows:
        raw_value = row.openrouter_api_key
        if not raw_value or not raw_value.startswith(ENCRYPTION_PREFIX):
            continue
        token = raw_value[len(ENCRYPTION_PREFIX):]
        decrypted = fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        conn.execute(
            sa.text("UPDATE users SET openrouter_api_key = :val WHERE id = :id"),
            {"val": decrypted, "id": row.id},
        )
