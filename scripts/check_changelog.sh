#!/bin/bash
# CI CHANGELOG check — mirrors the pre-commit hook's product-file gate.
# Usage: check_changelog.sh <base> <head>
# Exits 0 if no product-file changes, or if CHANGELOG.md is changed, or if
# any commit in the range contains [no-changelog].
# Otherwise prints offending files and exits 1.

set -euo pipefail

BASE="${1:-}"
HEAD="${2:-}"

if [[ -z "$BASE" || -z "$HEAD" ]]; then
    echo "Usage: $0 <base> <head>" >&2
    exit 1
done

# Escape hatch: any commit message in the range contains [no-changelog]
if git log --format=%s "$BASE..$HEAD" | grep -q '\[no-changelog\]'; then
    echo "Found [no-changelog] in commit messages — skipping CHANGELOG check."
    exit 0
fi

# Product-file patterns (must match scripts/pre-commit line 13)
PATTERN='^(ptos[^/]*\.py|desktop_app\.py|web_templates/.+|web_static/.+|starters/.+|schema\.toml|config\.toml)$'

CHANGED=$(git diff --name-only "$BASE..$HEAD" | grep -E "$PATTERN" || true)

if [[ -z "$CHANGED" ]]; then
    echo "No product-file changes in $BASE..$HEAD — CHANGELOG check passed."
    exit 0
fi

if echo "$CHANGED" | grep -q '^CHANGELOG\.md$'; then
    echo "CHANGELOG.md is present among product-file changes — check passed."
    exit 0
fi

echo ""
echo "ERROR: Product-file changes detected without CHANGELOG.md entry."
echo "Changed product files:"
echo "$CHANGED" | sed 's/^/  /'
echo ""
echo "Add a CHANGELOG.md entry (see AGENTS.md 'Changelog') or include"
echo "[no-changelog] in a commit message to skip."
exit 1