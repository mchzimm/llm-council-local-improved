#!/bin/bash
# Setup script to install git hooks and configure development environment
# Run this after cloning the repository

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/.git/hooks"

echo "Setting up LLM Council development environment..."

# Install pre-commit hook to prevent direct commits to master
cat > "$HOOKS_DIR/pre-commit" << 'EOF'
#!/bin/bash
# Git pre-commit hook to prevent direct commits to master branch
# Enforces the versioning workflow defined in AGENTS.md

BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
    echo ""
    echo "========================================================"
    echo "ERROR: Direct commits to '$BRANCH' are not allowed!"
    echo "========================================================"
    echo ""
    echo "Follow the versioning workflow in AGENTS.md:"
    echo ""
    echo "  1. Find highest version:"
    echo "     git branch -a | grep -oE 'v[0-9]+\\.[0-9]+\\.[0-9]+' | sort -V | tail -1"
    echo ""
    echo "  2. Create version branch BEFORE coding:"
    echo "     git checkout -b v<next-version>"
    echo ""
    echo "  3. Make your changes on the version branch"
    echo ""
    echo "  4. Commit and push to version branch:"
    echo "     git add -A && git commit -m 'v<version>: description'"
    echo "     git push -u origin v<version>"
    echo ""
    echo "  5. Merge to master (only after tests pass):"
    echo "     git checkout master && git merge v<version> && git push origin master"
    echo ""
    echo "To bypass this check (NOT RECOMMENDED), use: git commit --no-verify"
    echo "========================================================"
    echo ""
    exit 1
fi

# Validate branch naming convention (must be v<release>.<feature>.<fix>)
if [[ ! "$BRANCH" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo ""
    echo "========================================================"
    echo "WARNING: Branch '$BRANCH' doesn't follow version naming"
    echo "========================================================"
    echo ""
    echo "Expected format: v<release>.<feature>.<fix>"
    echo "Examples: v0.19.0, v1.0.0, v0.19.1"
    echo ""
    echo "This is a warning only - commit will proceed."
    echo "========================================================"
    echo ""
fi

exit 0
EOF

chmod +x "$HOOKS_DIR/pre-commit"
echo "✓ Installed pre-commit hook (prevents direct commits to master)"

echo ""
echo "Setup complete! Development environment is ready."
echo ""
echo "Remember: Always create a version branch before making changes."
echo "  git checkout -b v<version>"
