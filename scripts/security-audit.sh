#!/usr/bin/env bash
# =============================================================================
# security-audit.sh — pre-commit / CI security check
# Exits with code 1 if any issue is detected.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

red()   { echo -e "\033[0;31m[FAIL] $*\033[0m"; }
green() { echo -e "\033[0;32m[ OK ] $*\033[0m"; }
warn()  { echo -e "\033[0;33m[WARN] $*\033[0m"; }

echo "=== Security Audit: $(date) ==="
echo "Repository root: $REPO_ROOT"
echo ""

# -------------------------------------------------------------------------
# 1. Check for .env files that shouldn't be here
# -------------------------------------------------------------------------
echo "--- Checking for .env files ---"
ENV_FILES=$(find "$REPO_ROOT" \
  -not -path "$REPO_ROOT/.git/*" \
  -not -path "$REPO_ROOT/.venv/*" \
  \( -name ".env" -o -name ".env.*" \) \
  ! -name ".env.example" \
  2>/dev/null || true)

if [ -n "$ENV_FILES" ]; then
  red "Found .env file(s) that should NOT be committed:"
  echo "$ENV_FILES"
  ERRORS=$((ERRORS + 1))
else
  green "No stray .env files found"
fi

# -------------------------------------------------------------------------
# 2. Check for large binary files accidentally staged
# -------------------------------------------------------------------------
echo ""
echo "--- Checking for large binary files (MP3/MP4) ---"
BINARY_FILES=$(find "$REPO_ROOT" \
  -not -path "$REPO_ROOT/.git/*" \
  -not -path "$REPO_ROOT/.venv/*" \
  \( -name "*.mp3" -o -name "*.mp4" \) \
  2>/dev/null || true)

if [ -n "$BINARY_FILES" ]; then
  warn "Found binary media files (they are .gitignored, but should not be staged):"
  echo "$BINARY_FILES"
  # Check if any are actually staged
  if git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null | grep -qE '\.(mp3|mp4)$'; then
    red "Media files are STAGED — remove them before committing!"
    ERRORS=$((ERRORS + 1))
  else
    warn "Media files exist locally but are not staged (OK — just confirming .gitignore is working)"
  fi
else
  green "No MP3/MP4 files found in repo"
fi

# -------------------------------------------------------------------------
# 3. Check for hardcoded secret patterns in source files
# -------------------------------------------------------------------------
echo ""
echo "--- Scanning source files for secret patterns ---"

# Files to scan (exclude .git, .venv, binary, and this script itself)
SCAN_TARGETS=$(find "$REPO_ROOT" \
  -not -path "$REPO_ROOT/.git/*" \
  -not -path "$REPO_ROOT/.venv/*" \
  -not -name "*.sh" \
  -not -name ".env.example" \
  -not -name "security-audit.sh" \
  -type f \
  \( -name "*.py" -o -name "*.yml" -o -name "*.yaml" \
     -o -name "*.json" -o -name "*.toml" -o -name "*.md" \
     -o -name "*.txt" -o -name "*.cfg" -o -name "*.ini" \) \
  2>/dev/null || true)

SECRET_HITS=""
if [ -n "$SCAN_TARGETS" ]; then
  # Patterns to catch: actual values assigned to secret-like variable names
  SECRET_HITS=$(echo "$SCAN_TARGETS" | xargs grep -inE \
    '(api_key|apikey|secret_key|secretkey|access_token|auth_token|refresh_token|client_secret|private_key|password)\s*[=:]\s*["\047]?[A-Za-z0-9+/\-_]{16,}' \
    2>/dev/null | \
    grep -vE '(your-|<|>|example|placeholder|CHANGE_ME|TODO|sk-your|xxx|test|fake|dummy)' \
    || true)
fi

if [ -n "$SECRET_HITS" ]; then
  red "Possible hardcoded secrets detected:"
  echo "$SECRET_HITS"
  ERRORS=$((ERRORS + 1))
else
  green "No obvious hardcoded secrets found"
fi

# -------------------------------------------------------------------------
# 4. Check that .gitignore has all required entries
# -------------------------------------------------------------------------
echo ""
echo "--- Verifying .gitignore entries ---"
GITIGNORE="$REPO_ROOT/.gitignore"
REQUIRED_ENTRIES=(
  ".env"
  "*.mp3"
  "*.mp4"
  "episodes/"
  "credentials/"
  "token.json"
  "client_secret"
)

if [ ! -f "$GITIGNORE" ]; then
  red ".gitignore not found at $GITIGNORE"
  ERRORS=$((ERRORS + 1))
else
  for entry in "${REQUIRED_ENTRIES[@]}"; do
    if grep -qF "$entry" "$GITIGNORE"; then
      green ".gitignore contains: $entry"
    else
      red ".gitignore is MISSING entry: $entry"
      ERRORS=$((ERRORS + 1))
    fi
  done
fi

# -------------------------------------------------------------------------
# 5. Check for credential files accidentally committed
# -------------------------------------------------------------------------
echo ""
echo "--- Checking for OAuth/credential files ---"
CRED_FILES=$(find "$REPO_ROOT" \
  -not -path "$REPO_ROOT/.git/*" \
  -not -path "$REPO_ROOT/.venv/*" \
  \( -name "token.json" \
     -o -name "client_secret*.json" \
     -o -name "credentials.json" \) \
  2>/dev/null || true)

if [ -n "$CRED_FILES" ]; then
  warn "Credential files exist locally (verify they are NOT staged or committed):"
  echo "$CRED_FILES"
  if git -C "$REPO_ROOT" ls-files --error-unmatch $CRED_FILES 2>/dev/null; then
    red "Credential files are tracked by git — remove with: git rm --cached <file>"
    ERRORS=$((ERRORS + 1))
  fi
else
  green "No credential files found"
fi

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
echo ""
echo "=============================="
if [ "$ERRORS" -eq 0 ]; then
  green "All checks passed. Repository looks clean."
  exit 0
else
  red "$ERRORS issue(s) found. Fix them before committing."
  exit 1
fi
