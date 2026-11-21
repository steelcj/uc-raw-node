#!/bin/sh
# tools/check.sh: is the repository healthy?
#
#   tools/check.sh          the full check (the default), about 6 minutes
#   tools/check.sh --fast   the variable, syntax and gating lint checks, in
#                           seconds; what both git hooks run
#
# In order: tools/check_variables.py, ansible-playbook --syntax-check on
# every playbook, ansible-lint (if installed) gating on the entry playbooks
# and tasks/, then for the full check only an advisory ansible-lint of the
# whole repository (reported, not gating) and the stand-in test suite. The
# one rule turned off and the one directory excluded are in .ansible-lint,
# with their reasons.
# Every step runs even if an earlier one failed; each step prints one line
# and the exit status is non-zero if any failed.
#
# Needs ansible-playbook on the PATH (or ANSIBLE_PLAYBOOK set to it). If it
# is not there, tools/check.env is sourced when it exists. The
# variable check runs with the same Python as ansible-playbook, which has
# PyYAML. Logs go to artifacts/check/. Run from anywhere in the repository.
# This script is the authority for "is the repository healthy"; the git
# hooks in tools/git-hooks/ only call it.

set -u

mode=full
case "${1:-}" in
    ""|--full) mode=full ;;
    --fast) mode=fast ;;
    *) echo "usage: $0 [--fast|--full]" >&2; exit 2 ;;
esac

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root" || exit 2

# Find ansible-playbook without guessing: ANSIBLE_PLAYBOOK if set, else the
# PATH, else the PATH after sourcing tools/check.env (a gitignored sh file
# for this host, for example PATH="$HOME/.venvs/ansible/bin:$PATH").
if [ -z "${ANSIBLE_PLAYBOOK:-}" ] && ! command -v ansible-playbook >/dev/null 2>&1 \
        && [ -f tools/check.env ]; then
    # shellcheck source=/dev/null
    . ./tools/check.env
fi
playbook=${ANSIBLE_PLAYBOOK:-$(command -v ansible-playbook || true)}
if [ -z "$playbook" ] || [ ! -x "$playbook" ]; then
    echo "check.sh: ansible-playbook not found on the PATH${ANSIBLE_PLAYBOOK:+ or at ANSIBLE_PLAYBOOK=$ANSIBLE_PLAYBOOK}." >&2
    echo "check.sh: create tools/check.env (gitignored, sourced by sh) to put it on the PATH, for example:" >&2
    echo "check.sh:     PATH=\"\$HOME/.venvs/ansible/bin:\$PATH\"" >&2
    exit 2
fi
bindir=$(dirname "$playbook")
python=$(sed -n '1s/^#! *//p' "$playbook" | cut -d' ' -f1)
if [ -z "$python" ] || ! "$python" -c 'import yaml' 2>/dev/null; then
    python=${PYTHON:-python3}
fi

logs="$root/artifacts/check"
mkdir -p "$logs"
failed=0

step() {
    # step <name> <command...>: run a step, log its output, note the result.
    name=$1
    shift
    started=$(date +%s)
    if "$@" >"$logs/$name.log" 2>&1; then
        result=ok
    else
        result=FAIL
        failed=1
    fi
    line=$(printf '%-24s %-4s %4ss' "$name" "$result" $(( $(date +%s) - started )))
    echo "$line"
}

syntax_all() {
    status=0
    for file in build.yml validate.yml destroy.yml tests/*.yml; do
        if ! "$bindir/ansible-playbook" --syntax-check -i localhost, "$file" >/dev/null 2>&1; then
            echo "syntax check failed: $file"
            status=1
        fi
    done
    return $status
}

echo "check.sh: $mode check, logs in artifacts/check/"
step variables "$python" tools/check_variables.py
step syntax syntax_all

lint=
if command -v ansible-lint >/dev/null 2>&1 || [ -x "$bindir/ansible-lint" ]; then
    lint=$(command -v ansible-lint || echo "$bindir/ansible-lint")
    # Paths before --exclude, which takes several values.
    step ansible-lint "$lint" build.yml validate.yml destroy.yml tasks/ --exclude roles/
else
    line=$(printf '%-24s %-4s' ansible-lint skip)
    echo "$line (not installed)"
fi

if [ "$mode" = full ]; then
    if [ -n "$lint" ]; then
        "$lint" --nocolor -f pep8 >"$logs/ansible-lint-all.log" 2>&1
        found=$(grep -cE '^[^ ]+:[0-9]+' "$logs/ansible-lint-all.log")
        line=$(printf '%-24s %-4s' ansible-lint-all note)
        echo "$line $found findings in the whole repository (reported, not gating)"
    fi
    export PATH="$bindir:$PATH"
    step validate "$bindir/ansible-playbook" validate.yml \
        -e @tests/fixtures/raw-node-input.yml -e target_platform=incus_container_default
    step prepare_paths "$bindir/ansible-playbook" -i localhost, -c local tests/prepare_paths.yml
    step transport env PATH="$root/tests/bin:$PATH" \
        "$bindir/ansible-playbook" -i localhost, -c local tests/transport_incus_exec.yml \
        -e raw_node_test_destroy=true
    step build_scenarios "$bindir/ansible-playbook" -i localhost, -c local tests/build_scenarios.yml
    step destroy_scenarios "$bindir/ansible-playbook" -i localhost, -c local tests/destroy_scenarios.yml
    step attempt_history "$bindir/ansible-playbook" -i localhost, -c local tests/attempt_history.yml
fi

if [ $failed -ne 0 ]; then
    echo "check.sh: FAILED. See the logs in artifacts/check/ for the steps marked FAIL."
    exit 1
fi
echo "check.sh: all $mode checks passed."
