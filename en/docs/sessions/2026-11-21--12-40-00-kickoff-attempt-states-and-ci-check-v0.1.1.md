# Kickoff: Attempt States, Attempt History, Report Timeout and the CI Check

- **Version:** 0.1.1
- **Date:** 2026-11-21
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose

This is the kickoff prompt for a Claude Code session that brings uc-raw-node's code in line with *Raw Node Controller Layout Design* v0.1.10 (`en/docs/design/raw-node-controller-layout-design-v0.1.10.md`), then adds the CI check that document calls for. It follows the layout migration merged as pull request 1 and tagged `v0.2.0`. Paste everything under "Prompt" into Claude Code, started at the repository root on an up-to-date `main`.

## Prompt

You are working in the uc-raw-node repository, the raw node controller. The layout migration is merged. Your job is to implement the three decisions that layout design v0.1.10 lists as "not yet in the code", then write the CI check for variable names and secret handling, in the phases below.

### Read first

Read these before changing anything, in this order:

- `en/docs/design/raw-node-controller-layout-design-v0.1.10.md`, the authority for this work. The parts that matter most are One attempt per hostname, The attempt record, Waiting for the report, Failure handling order, Transport obligations, First release decisions and Variables.
- `README.md`
- `en/docs/sessions/README.md`, for how session records are named. Follow it for every file you write in `en/docs/sessions/`.
- `en/docs/sessions/2026-11-21--11-06-57-session.md`, the record of the migration, for how the tests and stand-in client work and what was found then.
- Everything under `tasks/`, `roles/` and `tests/`, and the three entry playbooks.

When the design document and the code disagree, the design wins. When the design is silent, use the defaults under "Gaps in v0.1.10" below, or stop and ask.

### Ground rules

- Work on a new branch from `main`, `attempt-states-and-ci`. Commit at the end of each phase, with a message naming the phase. Do not push or open a pull request unless I ask.
- Target ansible-core 2.21.6, the version the migration was tested on, and keep to features available in 2.15 where that costs nothing. Use fully qualified module names.
- Keep every rule from the migration: `no_log: true` on anything that reads, writes or delivers the payload or refers to the secrets path; the masked-task rule for failure reasons; no contract values, hashes or tokens in output, records or failure messages.
- After each phase, run the checks listed for it, then the full stand-in test suite (`tests/prepare_paths.yml`, `tests/transport_incus_exec.yml`, `tests/build_scenarios.yml`, `tests/destroy_scenarios.yml`, and `validate.yml` on the fixture), and fix what fails before moving on.
- Markdown you write follows the house style: commas rather than em dashes, no heading numbers, no horizontal rules, no hard line wraps in prose, subsections as headings rather than bolded lead-ins.
- Create the session record at the start (see Phase 6) and keep adding to it as you go.

### Gaps in v0.1.10, with the defaults to use

These were found by comparing v0.1.10 with the code on `main`. Apply the default unless I say otherwise, and list each one in the session record so it can go into layout design v0.1.11.

- **How the controller knows whether the transport created anything.** v0.1.10 says `handle_failure.yml` sets `aborted` when "the transport created nothing in this run", but the only facts that say so are Incus-specific (`raw_node_incus_launched`, `raw_node_incus_adopted`), and the controller must never read a transport-specific variable. Default: every transport sets one generic fact, `raw_node_transport_state`, with three values. It is `none` at the very start of the transport, before any check that can fail. It becomes `adopted` once the transport has decided to use an existing instance and before it changes anything in it. It becomes `created` immediately before the command that creates an instance, so a launch that fails halfway still counts as created and gets torn down. `handle_failure.yml` treats an undefined value (the build failed before the transport ran, for example in `payload.yml`) the same as `none`. Then: `none` means `aborted` and no teardown, `adopted` means `quarantined`, and `created` means the existing destroy-or-quarantine path by `can_destroy`. This widens the naming table's transport output row to `raw_node_transport_*`, and adds a line to Transport obligations.
- **Starting a new attempt while a node may still exist.** v0.1.10 moves an earlier attempt's records into history when a new attempt starts. It does not say what happens when the current attempt is `confirmed` or `quarantined`, or was left `in_progress` or `failed` by a run that died. In all four states a node may still exist. If the new attempt then fails or aborts, the live node's confirmation or failure record would only be found in `history/`, and the current record would wrongly suggest there is no node. Default: `write_attempt.yml` refuses to start when the current attempt is in one of those four states. It stops before moving anything, with a message naming the state and telling the operator to destroy the node first, or to pass `-e raw_node_attempt_replace=true` if they know it is gone. It proceeds without asking when the current state is `aborted` or `destroyed`, or there is no record.
- **Naming the history folder.** v0.1.10 names it `records/<hostname>/history/<started>/`, after the earlier attempt's start time. But `set_attempt_state.yml` can write a record without `started` (`destroy.yml -e target_platform` on another host), and `started` contains colons. Default: use `started`, falling back to `updated` and then to the time of the move. Write the timestamp in the sessions convention's file-safe form, `YYYY-MM-DD--HH-MM-SS`. Add `-2`, `-3` and so on if the folder already exists.
- **The report timeout parameter's name.** v0.1.10 says `wait_phone_home.yml` passes the timeout to the transport as an include parameter, but gives the parameter no name. A transport-specific name such as `raw_node_incus_address_timeout` would make the controller read Incus names. Default: `wait_phone_home.yml` passes `raw_node_transport_address_timeout: "{{ raw_node_report_timeout }}"` with `vars:` on its `include_role`. Every transport's `address.yml` reads that generic name, and falls back to its own default only when it is not given. The Incus role's default then stops reading `raw_node_report_timeout`.

### Phase 1: The aborted state

- Add `raw_node_transport_state` to `raw_node_transport_incus_exec` as described above. Keep `raw_node_incus_launched` and `raw_node_incus_adopted`, since the transport's own `destroy.yml` reads them, but set them in the same places so the two can never disagree.
- Change `handle_failure.yml` to choose between abort, quarantine and destroy from `raw_node_transport_state`. For `none` or undefined: skip teardown, set the state to `aborted`, record `action: abort` in the failure record, and print no alert. Still delete the secrets and still end the run with the original failure.
- Update the `build.yml` comment block if what it says about failure handling changes.
- Update the transport's README with the new fact.

Checks: extend `tests/build_scenarios.yml`.

- The `placeholders` scenario now ends `aborted`, with `action: abort` and nothing launched.
- A new `refused_existing` scenario does this: launch an unmarked instance under the fixture's hostname, run the build, expect `aborted` with the instance untouched, then delete the instance by hand.
- A new `adopted_failure` scenario does this: launch an unmarked instance and build with `-e raw_node_incus_allow_existing=true` and the failing stand-in payload. Expect `quarantined`, with the instance still there.
- `payload_failure` still ends `destroyed`, and `teardown_failure` still ends `quarantined`.

### Phase 2: Attempt history

- In `write_attempt.yml`, before writing the new record, read the current `attempt.yml` if there is one. Refuse in the four states listed above unless `raw_node_attempt_replace` is true. Otherwise move `attempt.yml`, `failure.yml` and `confirmation.yml`, whichever exist, into the history folder named as above, then write the new record. Reports stay where they are and are overwritten.
- The move happens before the block, so a failure inside it ends the run with nothing to clean up, as for every step before the block. Make sure a half-finished move cannot leave the current folder without an `attempt.yml` while the history folder holds one: copy into the history folder first, then remove the originals.
- Document in the README, in the operational notes on records, that the orchestration controller must read `attempt.yml` and accept `confirmation.yml` only when the state is `confirmed`. Also document the history folders and `raw_node_attempt_replace`.

Checks: a new runner, `tests/attempt_history.yml` (or new scenarios in the build runner, whichever fits the existing helpers better), covering:

- Two builds in a row where the first ends `aborted`: the second proceeds, and the first attempt's `attempt.yml` and `failure.yml` are in one history folder.
- A `confirmed` build followed by a second build: refused before anything moves, and the records are unchanged.
- The same with `-e raw_node_attempt_replace=true`: proceeds, and the confirmed attempt's files are in history.
- A record without `started`, written by a standalone destroy: the history folder is named from `updated`.
- Two moves in the same second: the second folder gets `-2`.
- A record left `in_progress`: refused.

### Phase 3: Report timeout as a parameter

- Pass `raw_node_transport_address_timeout` from `wait_phone_home.yml` as described above, and change the Incus role's `address.yml` and `defaults/main.yml` to use it. `main.yml`'s own wait before the payload keeps using `raw_node_incus_wait_timeout`.
- The failure message for `no_report` keeps naming `raw_node_report_timeout`'s value.

Checks: with the stand-in client, run `tests/build.yml` with `-e raw_node_report_timeout=7`. Confirm from the report or the transport's `waited` field that the transport used 7. Then grep the role to confirm nothing under `roles/` reads `raw_node_report_timeout` any more. If the stand-in client can be made to drop the instance's address after the payload runs, add the `no_report` scenario that the migration could not test. If it can't, say so in the session record.

### Phase 4: The CI check

Write the check that v0.1.10's Variables section describes, as a plain script that runs anywhere Python and the repository are available. Do not use GitHub Actions or any other hosted or proprietary CI service: the check runs locally, through git's own hooks, so it works the same on any host and with any remote.

- `tools/check_variables.py`, using only the standard library and PyYAML, which ansible-core already requires. It scans `tasks/`, `roles/` and the three entry playbooks, and collects every name set by `set_fact` (`ansible.builtin.set_fact` or `set_fact`, ignoring `cacheable`) or `register`.
- Prefix rules: the table in v0.1.10, encoded once in the script as data (row pattern, allowed files), with `raw_node_transport_*` widened as in Phase 1. A name fails if it matches no row, or if it is set in a file its row does not allow. `target_platform` is accepted only from `destroy.yml`.
- Secret rules: fail on any task without `no_log: true` whose module arguments (not its `name`) contain a template referring to `raw_node_secrets_dir`, `raw_node_secrets_path`, `raw_node_payload_file`, `raw_node_input` or a token variable. Also fail if any file under `templates/` contains `set -x` or `set -o xtrace`. Assertion tasks whose messages name the setting in plain text, not in a template, must pass, as v0.1.10's "Masked messages" rule intends.
- Escape hatch: a task may carry a comment `# ci-allow: <rule> <reason>` on the line before it, and the script reports every allowance it honours, so exceptions stay visible. Use it only where the rule is wrong for that task, and list every use in the session record.
- Output: one line per problem with file, task name and rule, a summary count, and a non-zero exit on any problem.
- `tools/check.sh` runs, in order: the variable check, `ansible-playbook --syntax-check` on every playbook, `ansible-lint` if it is installed (with a note if not), and the stand-in test suite. This is the one command for "is the repository healthy".
- `tools/git-hooks/pre-commit` runs the fast part: the variable check and the syntax checks, which take seconds. `tools/git-hooks/pre-push` runs all of `tools/check.sh`, including the stand-in test suite. Both are plain POSIX `sh` scripts that call `tools/check.sh` with an option choosing the fast or full set, so the hooks contain no logic of their own.
- The hooks are versioned in the repository and enabled per clone with `git config core.hooksPath tools/git-hooks`, a standard git setting that needs no extra tool. Add `tools/install-hooks.sh`, which runs that command and checks the hooks are executable, and say in the README that each clone runs it once.
- A hook is a local guard, not an enforcement point: `git commit --no-verify` skips it. Say so in the README, and say that `tools/check.sh` is the authority, to be run in full before merging to `main`.
- Do not add the `pre-commit` framework or any other hook manager. Plain git hooks are enough, and they add no dependency.

Checks: after `tools/install-hooks.sh`, confirm that a commit runs the fast check and a push attempt runs the full check (use `git push --dry-run` to a local bare repository under `artifacts/`, not to GitHub). Run the script on the current code and fix what it finds. A real violation is fixed in the code. A rule that turns out to be wrong for a whole class of tasks is a gap to report: list it in the session record and stop and ask before changing the rule. Show the script failing on a deliberate violation of each rule (an unlisted prefix, a name set in a second file, a secrets task without `no_log`, `set -x` in a template), then remove the violations.

### Phase 5: ansible-lint

- Install ansible-lint with `pipx install ansible-lint`, or in the same virtual environment as ansible-core if pipx is not available, and record the version.
- Run it on the whole repository with the default profile. Fix real findings. For findings you judge wrong for this repository, add the narrowest possible `# noqa: <rule>` with a reason on the same line, never a blanket skip in a config file, and list each one in the session record.
- If the number of findings is large (more than about 40), fix the ones in `tasks/` and the entry playbooks, and list the rest in the session record as follow-up, rather than spending the session on lint.

### Phase 6: Documents and session record

- Update `README.md`: the status table, the operational notes on records (Phase 2), `tools/check.sh`, the hooks and how to enable them, and the attempt states.
- Update the Incus transport's README for `raw_node_transport_state` and `raw_node_transport_address_timeout`.
- Do not write layout design v0.1.11. I will write it from your session record.
- The session record goes in `en/docs/sessions/`, named `$(date +%Y-%m-%d--%H-%M-%S)-session.md` when you create it at the start of the session. By the end it holds: what each phase did; how each gap default turned out; every `ci-allow` and `noqa` with its reason; anything else that departs from v0.1.10 or that it does not cover; the test summary; and open questions for me.

### Phase 7: Real Incus host

Run only if `incus info` succeeds. Use the existing `uc-raw-node-test` project, with `-e raw_node_incus_project=uc-raw-node-test -e raw_node_incus_image=images:debian/13` on every run. Never delete anything outside that project.

- Run `tests/build_scenarios.yml` and `tests/destroy_scenarios.yml` with `-e raw_node_test_stand_in=false`, plus the attempt history runner if it can run against real Incus.
- Check the new `refused_existing` and `adopted_failure` scenarios on the real host in particular, since they create and leave instances that the controller must not delete.
- Leave the project empty at the end and say so in the session record.

Final check: run `tools/check.sh` once more from a clean `artifacts/`, and put its summary in the session record.

### When to stop and ask

Stop and ask before going on if:

- A gap default turns out not to work, or would need a transport to read a controller variable or the controller to read a transport-specific one.
- A CI rule is wrong for a whole class of tasks rather than for one task.
- A check fails and the fix would change a step contract in v0.1.10 beyond the gaps listed above.
- You would need to change anything outside `tasks/`, `roles/`, `tests/`, `tools/` (including `tools/git-hooks/`), the entry playbooks, `vars/defaults.yml`, `README.md`, the transport's README and your session record.

## Changes

### From v0.1.0 to v0.1.1

- Replaced the GitHub Actions workflow with versioned plain git hooks in `tools/git-hooks/`, enabled per clone with `core.hooksPath` through `tools/install-hooks.sh`: `pre-commit` runs the fast checks and `pre-push` the full `tools/check.sh`. Ruled out hosted or proprietary CI services and hook managers.
- Added a check that the hooks run, using a local bare repository instead of GitHub, and the hooks to the README update and to the paths Claude Code may change.
