#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the lab_data_integrations_interface repo.
# Prepares the uv-managed Python 3.11 workspace and the Next.js UI.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# 1. uv (Python package/toolchain manager). Skip the download if already present.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2. Pin the interpreter the repo requires (>=3.11,<3.12).
uv python install 3.11

# 3. Sync the Python workspace: dev tools (ruff, pyright, complexipy, vulture,
#    pre-commit) plus the testing extra (pytest, faker). Mirrors CI.
uv sync --group dev --extra testing

# 4. Pre-install the pre-commit hook environments so the first lint run is fast
#    and offline-safe. Non-fatal if it cannot reach the network.
uv run pre-commit install-hooks || true

# 5. Next.js UI dependencies.
npm ci --prefix ui

# 6. Seed a local UI env file so the dev server can boot out of the box.
#    Values are non-functional placeholders (valid URL/key shapes so the client
#    initializes); replace them with a real Supabase project for authenticated
#    flows. See ui/.env.local.example.
if [ ! -f ui/.env.local ]; then
  cat > ui/.env.local <<'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://placeholder-ref.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_placeholder_key_for_local_dev
EOF
fi
