#!/bin/sh
# Enables the versioned git hooks in tools/git-hooks/ for this clone, by
# pointing git's core.hooksPath at that folder. Run once per clone. Needs
# only git. To turn the hooks off again: git config --unset core.hooksPath
set -eu
root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$root"
for hook in tools/git-hooks/*; do
    if [ ! -x "$hook" ]; then
        echo "install-hooks: $hook is not executable; run chmod +x $hook" >&2
        exit 1
    fi
done
git config core.hooksPath tools/git-hooks
echo "install-hooks: core.hooksPath is now tools/git-hooks for $root"
echo "install-hooks: pre-commit runs tools/check.sh --fast, pre-push runs tools/check.sh --full"
