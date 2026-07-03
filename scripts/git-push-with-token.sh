#!/bin/bash
# Push текущей ветки в origin, используя токен из .env
# Использование: ./scripts/git-push-with-token.sh [branch]
# Если branch не указан — пушит текущую ветку.

set -euo pipefail

TOKEN_FILE="/home/node/.openclaw/workspace/.env"
REPO="volodkindv/la_searcher_bot.git"

if [ ! -f "$TOKEN_FILE" ]; then
    echo "❌ Файл $TOKEN_FILE не найден" >&2
    exit 1
fi

TOKEN=$(grep ^GITHUB_TOKEN "$TOKEN_FILE" | cut -d= -f2-)
if [ -z "$TOKEN" ]; then
    echo "❌ GITHUB_TOKEN не найден в $TOKEN_FILE" >&2
    exit 1
fi

BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"
echo "🚀 Push $BRANCH → origin/$BRANCH"

git push "https://oauth2:TOKEN}@github.com/$REPO" "$BRANCH"

git remote set-url origin "https://github.com/$REPO"
echo "✅ Готово. Remote очищен от токена."
