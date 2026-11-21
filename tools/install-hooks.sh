#!/bin/sh
# Enables the versioned git hooks in tools/git-hooks/ for this clone, by
# pointing git's core.hooksPath at that folder. Run once per clone. Needs
# only git. To turn the hooks off again: git config --unset core.hooksPath
#
# The hooks run tools/check.sh, which needs ansible-playbook. This script
# checks it can be found the same way check.sh finds it (ANSIBLE_PLAYBOOK,
# the PATH, or the PATH after sourcing tools/check.env), and says how to fix
# it if not. The hooks are enabled either way.
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
echo "install-hooks: pre-commit and pre-push both run tools/check.sh --fast; run the full tools/check.sh by hand before merging to main"

found=$(
    if [ -z "${ANSIBLE_PLAYBOOK:-}" ] && ! command -v ansible-playbook >/dev/null 2>&1 \
            && [ -f tools/check.env ]; then
        # shellcheck source=/dev/null
        . ./tools/check.env
    fi
    playbook=${ANSIBLE_PLAYBOOK:-$(command -v ansible-playbook || true)}
    if [ -n "$playbook" ] && [ -x "$playbook" ]; then echo "$playbook"; fi
)
if [ -z "$found" ]; then
    echo "install-hooks: ansible-playbook not found, so the hooks will fail until it is." >&2
    echo "install-hooks: create tools/check.env (gitignored, sourced by sh) to put it on the PATH, for example:" >&2
    echo "install-hooks:     PATH=\"\$HOME/.venvs/ansible/bin:\$PATH\"" >&2
    exit 1
fi
echo "install-hooks: the hooks will use $found"
