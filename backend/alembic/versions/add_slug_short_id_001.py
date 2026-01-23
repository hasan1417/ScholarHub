"""Add slug and short_id to projects and research_papers

Revision ID: add_slug_short_id_001
Revises: add_ai_memory_001
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
import secrets
import string
import re

# revision identifiers, used by Alembic.
revision = 'add_slug_short_id_001'
down_revision = 'add_ai_memory_001'
branch_labels = None
depends_on = None

# Characters for short IDs (URL-safe, no ambiguous chars)
SHORT_ID_CHARS = 'abcdefghijkmnpqrstuvwxyz23456789'


def generate_short_id(length=8):
    return ''.join(secrets.choice(SHORT_ID_CHARS) for _ in range(length))


def slugify(text, max_length=50):
    if not text:
        return ""
    slug = text.lower()
    slug = slug.replace('&', 'and').replace('@', 'at').replace('+', 'plus')
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    if len(slug) > max_length:
        slug = slug[:max_length]
        last_hyphen = slug.rfind('-')
        if last_hyphen > max_length // 2:
            slug = slug[:last_hyphen]
    return slug


def upgrade():
    # Add columns to projects
    op.add_column('projects', sa.Column('slug', sa.String(300), nullable=True))
    op.add_column('projects', sa.Column('short_id', sa.String(12), nullable=True))
    op.create_index('ix_projects_slug', 'projects', ['slug'])
    op.create_index('ix_projects_short_id', 'projects', ['short_id'], unique=True)

    # Add columns to research_papers
    op.add_column('research_papers', sa.Column('slug', sa.String(300), nullable=True))
    op.add_column('research_papers', sa.Column('short_id', sa.String(12), nullable=True))
    op.create_index('ix_research_papers_slug', 'research_papers', ['slug'])
    op.create_index('ix_research_papers_short_id', 'research_papers', ['short_id'], unique=True)

    # Populate existing records with slugs and short_ids
    conn = op.get_bind()

    # Update projects
    projects = conn.execute(sa.text("SELECT id, title FROM projects WHERE short_id IS NULL")).fetchall()
    for project in projects:
        short_id = generate_short_id()
        slug = slugify(project[1]) if project[1] else ""
        conn.execute(
            sa.text("UPDATE projects SET slug = :slug, short_id = :short_id WHERE id = :id"),
            {"slug": slug, "short_id": short_id, "id": project[0]}
        )

    # Update research_papers
    papers = conn.execute(sa.text("SELECT id, title FROM research_papers WHERE short_id IS NULL")).fetchall()
    for paper in papers:
        short_id = generate_short_id()
        slug = slugify(paper[1]) if paper[1] else ""
        conn.execute(
            sa.text("UPDATE research_papers SET slug = :slug, short_id = :short_id WHERE id = :id"),
            {"slug": slug, "short_id": short_id, "id": paper[0]}
        )


def downgrade():
    # Remove indexes and columns from research_papers
    op.drop_index('ix_research_papers_short_id', 'research_papers')
    op.drop_index('ix_research_papers_slug', 'research_papers')
    op.drop_column('research_papers', 'short_id')
    op.drop_column('research_papers', 'slug')

    # Remove indexes and columns from projects
    op.drop_index('ix_projects_short_id', 'projects')
    op.drop_index('ix_projects_slug', 'projects')
    op.drop_column('projects', 'short_id')
    op.drop_column('projects', 'slug')
