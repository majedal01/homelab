#!/usr/bin/env bash
# Regenerate `lib/api-types.ts` from FastAPI's OpenAPI schema.
# Usage:
#   API_URL=http://localhost:8000 ./scripts/generate-types.sh
#
# CI invokes this and then `git diff --exit-code` on lib/api-types.ts to
# catch schema drift.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
OUT="lib/api-types.ts"

npx --yes openapi-typescript "${API_URL}/openapi.json" -o "${OUT}"

echo "Wrote ${OUT}"
