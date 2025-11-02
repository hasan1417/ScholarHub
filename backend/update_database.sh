#!/bin/bash
# ScholarHub Database Update Script
# Usage: ./update_database.sh

set -euo pipefail  # Exit on any error; treat unset as error

echo "🔄 Starting ScholarHub database update..."

# Navigate to backend directory
cd "$(dirname "$0")"

# Activate virtual environment (scholarenv -> venv fallback)
echo "📦 Activating virtual environment..."
if [ -f scholarenv/bin/activate ]; then
  # shellcheck disable=SC1091
  source scholarenv/bin/activate
elif [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
else
  echo "⚠️  No virtualenv found (scholarenv/venv). Continuing if dependencies are globally available..."
fi

# Check if PostgreSQL is reachable
echo "🔍 Checking database connectivity..."
if command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -q '^scholarhub-postgres-1$'; then
    if docker exec scholarhub-postgres-1 pg_isready -U scholarhub >/dev/null 2>&1; then
      echo "✅ PostgreSQL (docker) is running"
    else
      echo "❌ Docker Postgres container is not ready. Start with: docker-compose up -d postgres"
      exit 1
    fi
  else
    echo "ℹ️  Docker is available but container 'scholarhub-postgres-1' not found; will try Alembic directly."
  fi
fi

# Try a lightweight Alembic command to verify connection
if ! alembic current >/dev/null 2>&1; then
  echo "❌ Database connection failed via Alembic. Ensure DATABASE_URL is set and DB is reachable."
  echo "   Current DATABASE_URL: ${DATABASE_URL:-'(not set)'}"
  exit 1
fi
echo "✅ Database connection OK"

# Show current migration status
echo "📊 Current migration status:"
alembic current

# Show pending migrations
echo "📋 Checking for pending migrations..."
CURRENT=$(alembic current 2>/dev/null | head -1 | awk '{print $1}')
HEAD=$(alembic show head 2>/dev/null | grep -E "^Rev:" | awk '{print $2}')

if [ "${CURRENT:-none}" = "${HEAD:-none}" ]; then
    echo "✅ Database is already up to date (at HEAD: $HEAD)"
else
    echo "⏳ Pending migrations found. Current: $CURRENT, Head: $HEAD"
    # Non-interactive apply unless NO_APPLY=1 is set
    if [ "${NO_APPLY:-0}" = "1" ]; then
      echo "⏸️  Skipping apply due to NO_APPLY=1"
      exit 0
    fi
    echo "🚀 Applying migrations..."
    alembic upgrade head
    echo "✅ Migrations applied successfully!"
fi

# Show final status
echo "📊 Final migration status:"
alembic current

echo "🎉 Database update complete!"
