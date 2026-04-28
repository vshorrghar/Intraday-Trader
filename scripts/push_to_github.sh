#!/bin/bash
# Push Wealth Builder Pro to GitHub as private repo
# Run this ON EC2 (not Mac)
#
# BEFORE running this script:
# 1. Go to https://github.com/settings/tokens
# 2. Click "Generate new token (classic)"
# 3. Give it a name like "wealth-builder-ec2"
# 4. Check the "repo" scope (full control of private repos)
# 5. Click Generate → copy the token
# 6. Run this script and paste the token when asked

set -e

REPO_NAME="wealth-builder-pro"
GITHUB_USER="vshorgha"

cd ~/wealth-builder-pro

echo ""
echo "🔐 GitHub Setup"
echo "==============="
echo ""
echo "Paste your GitHub Personal Access Token:"
read -s GITHUB_TOKEN
echo ""

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ No token provided"; exit 1
fi

# Install git if needed
if ! command -v git &> /dev/null; then
    echo "📦 Installing git..."
    sudo yum install -y git
fi

# Create repo on GitHub using API
echo "📦 Creating private repo on GitHub..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST https://api.github.com/user/repos \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    -d "{\"name\":\"$REPO_NAME\",\"private\":true,\"description\":\"Personal portfolio intelligence for Indian markets\"}")

if [ "$RESPONSE" = "201" ]; then
    echo "  ✅ Repo created: github.com/$GITHUB_USER/$REPO_NAME (private)"
elif [ "$RESPONSE" = "422" ]; then
    echo "  ℹ️  Repo already exists, will push to it"
else
    echo "  ⚠️  HTTP $RESPONSE — trying to push anyway"
fi

# Init git and push
echo ""
echo "📤 Pushing code..."

git init
git config user.email "vshorrghar@gmail.com"
git config user.name "vshorgha"

git add -A
git commit -m "Initial commit — Wealth Builder Pro" 2>/dev/null || echo "  (nothing new to commit)"

git remote remove origin 2>/dev/null || true
git remote add origin "https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"

git branch -M main
git push -u origin main --force

echo ""
echo "=============================="
echo "✅ DONE!"
echo "=============================="
echo "Repo: https://github.com/$GITHUB_USER/$REPO_NAME"
echo "(Private — only you can see it)"
echo ""

# Clean up token from remote URL for security
git remote set-url origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"
