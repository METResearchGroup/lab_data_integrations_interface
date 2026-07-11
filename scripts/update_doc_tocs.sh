#!/usr/bin/env bash
# Run doctoc on markdown files under docs/adrs, docs/design_docs, and
# strategy_planning. Intended for use as a pre-commit hook (receives staged
# filenames as arguments).
set -euo pipefail

if [[ $# -eq 0 ]]; then
  exit 0
fi

matched=()
for f in "$@"; do
  if [[ "$f" =~ ^(docs/adrs|docs/design_docs|strategy_planning)/.+\.md$ ]]; then
    matched+=("$f")
  fi
done

if [[ ${#matched[@]} -eq 0 ]]; then
  exit 0
fi

npx --yes doctoc@2 "${matched[@]}"
