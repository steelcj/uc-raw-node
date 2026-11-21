# Kickoff: Controller Layout Migration

- **Version:** 0.1.3
- **Date:** 2026-11-21
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose

This is the kickoff prompt for a Claude Code session that implements *Raw Node Controller Layout Design* v0.1.8 (`en/docs/design/raw-node-controller-layout-design-v0.1.8.md`) in uc-raw-node. Paste everything under "Prompt" into Claude Code, started at the repository root.

## Prompt

You are working in the uc-raw-node repository, the raw node controller. Your job is to move the repository from its current layout (a `raw_node_controller` role) to the layout in `en/docs/design/raw-node-controller-layout-design-v0.1.8.md`, and to build the steps that layout adds, in the phases below.

### Read first

Read these before changing anything, in this order:

- `en/docs/design/raw-node-controller-layout-design-v0.1.8.md`, the authority for this work. Its Migration section is your checklist.
- `README.md`
- `en/docs/sessions/README.md`, for how session records and kickoffs are named. Follow it for every file you write in `en/docs/sessions/`.
- `en/docs/collapsable-strategy-for-a-raw-node-controller-v0.1.10.md` and `en/docs/1-the-platform-registry-v0.1.4.md`, for what the controller does. Do not change behaviour they define.
- Everything under `roles/` and `tests/`.

When the design document and the code disagree, the design wins. When the design document is silent or contradicts itself, do not invent a design: use the defaults given under "Known gaps" below, or stop and ask.

### Priorities

Two kinds of raw node matter first, in this order:

- **Priority 1: a Debian 13 container on a local Incus server.** This is the registry entry `incus_container_default` (`adopt` strategy, `incus_exec` transport) with the image `images:debian/13`. Everything in this kickoff is aimed at it, and its real-host run (Phase 7) is the acceptance test for this work.
- **Priority 2: a Debian 13 VPS.** Not built in this session. It will need a new transport, and probably a strategy other than `adopt`. Do not add a registry entry or a transport for it. Do not make choices that only work because Incus is local and on the same host, either: anything a transport records or checks about its own instances must be something a cloud provider transport could also do. For example, Incus user keys could be tags on a cloud instance.

### Ground rules

- Work on a new branch, `layout-migration`. Commit at the end of each phase, with a message naming the phase. Do not push or open a pull request unless I ask.
- Target ansible-core 2.22, while keeping to features available in 2.15 where that costs nothing. Use fully qualified module names (`ansible.builtin.*`).
- Keep existing variable names that already work. New variables follow the prefix table in the design's Variables section.
- Every task that reads, writes or delivers the payload, or refers to the secrets path or the token, carries `no_log: true`. A `no_log` task whose failure must be described follows the "Failure reasons from masked tasks" rule: register with `failed_when: false`, then a separate task sets `raw_node_failure_reason` from safe fields only and fails.
- Never print contract values, password hashes or the token, including in `debug` tasks and failure messages.
- After each phase, run the checks listed for it and fix what fails before moving on. If `ansible-lint` is available, run it on what you changed and fix real findings; do not add blanket skips.
- Markdown you write follows the house style: commas rather than em dashes, no heading numbers, no horizontal rules, no hard line wraps in prose, subsections as headings rather than bolded lead-ins.

### Known gaps in v0.1.8, with the defaults to use

These were found by comparing the design with the code. Apply the default unless I say otherwise, and list each one in the session record (see Phase 6) so it can go into v0.1.9.

- **Paths when playbooks run from `tests/`.** `vars/defaults.yml` builds paths from `playbook_dir`, which is `tests/` when a test playbook runs, so `{{ playbook_dir }}/registry/base.yml` would point to `tests/registry/base.yml`. Default: add `raw_node_root: "{{ playbook_dir }}"` to `vars/defaults.yml`, build every repository-relative path from `raw_node_root`, and set `raw_node_root: "{{ playbook_dir }}/.."` in `tests/vars/output.yml`. Test playbooks include task files as `../tasks/<file>.yml` and load `../vars/defaults.yml`.
- **Role search path for tests.** The design says `ansible.cfg` does not need `roles_path`, but that only holds for playbooks at the repository root. Default: keep `roles_path = ./roles` in `ansible.cfg`, and note that tests are run from the repository root.
- **Ownership check in standalone teardown.** `raw_node_transport_incus_exec/tasks/destroy.yml` decides whether it created an instance from `raw_node_transport_result`, which exists only in the run that built the node. Standalone `destroy.yml` has no such fact, and the attempt record as specified does not say whether the instance was created. Default: when the transport launches an instance, it sets an Incus user key on it (`--config user.uc-raw-node.created=true` plus `user.uc-raw-node.hostname=<hostname>`), and `destroy.yml` in the transport deletes only an instance carrying that key with a matching hostname. Ownership then lives on the platform itself and works from any controller host. Keep the in-run check as well, so an adopted instance is never deleted even if the key is somehow present. Describe this in the role's README as the transport's ownership marker, a rule every transport follows with whatever its platform offers (Incus user keys here, instance tags on a cloud provider), so the priority 2 transport inherits the rule rather than a new design.
- **Steps not yet buildable.** `payload.yml` needs the `RN-*` clauses pinned down, and `raw_node_validator` has not been started; the README lists both as not started, and they are out of scope here. Default: create `tasks/payload.yml` and `roles/raw_node_validator/tasks/main.yml` as placeholders that fail with a clear "not implemented yet" message, unless a test override is set (see Phase 4). Do not write a real payload template or validator.

### Phase 1: Move the structure

Follow the first part of the design's Migration section:

- Create `vars/defaults.yml` from `roles/raw_node_controller/defaults/main.yml`, with paths built from `raw_node_root`, and add the four output path settings exactly as the design gives them (`raw_node_records_path`, `raw_node_reports_path`, `raw_node_logs_path`, `raw_node_secrets_path`). Remove `raw_node_artifacts_dir` from the defaults.
- Move `files/registry.yml` to `registry/base.yml` and update `raw_node_registry_files`. Add `registry/clients/vishpala.yml` as an empty client layer with a comment saying what a client layer is for, only if the registry loader accepts an empty layer; otherwise leave it out and note why.
- Move `validate_registry.yml`, `load_registry_layer.yml`, `load_input.yml` and `resolve_platform.yml` to `tasks/`, changing only paths. Check `resolve_platform.yml` asserts the transport is in `raw_node_known_transports`, as the design requires, and add the assertion if it is missing.
- Use `git mv` for moves so history follows the files.
- Create `validate.yml` (the first three tasks of `build.yml` and nothing else).
- Remove `roles/raw_node_controller/`.
- Update `tests/transport_incus_exec.yml` to include the task files from `tasks/` instead of the role, and to load `../vars/defaults.yml` then `vars/output.yml` through `vars_files`.
- Add `tests/vars/output.yml`, pointing records, reports, logs and the secrets path into `artifacts/`, and setting `raw_node_root`.
- Add `records/`, `reports/` and `logs/` to `.gitignore`, keeping `artifacts/`.

Checks: `ansible-playbook validate.yml -e @tests/fixtures/raw-node-input.yml -e target_platform=incus_container_default` passes. `ansible-playbook --syntax-check` passes on every playbook. `grep -rn raw_node_controller` finds nothing outside `en/docs/`.

### Phase 2: Paths, secrets checks and the attempt record

- Write `tasks/prepare_paths.yml` as specified under "Handling sensitive files": expand every output path once with `expanduser` into separate names (`raw_node_records_dir`, `raw_node_reports_dir`, `raw_node_logs_dir`, `raw_node_secrets_dir`), create the per-hostname directories, create missing secrets directories one level at a time with mode `0700`, stop if the secrets path or the node's secrets directory already exists with looser permissions, and leave existing parents such as `~/.secrets` alone.
- Implement the two-step repository check exactly as written: resolve both paths with `realpath` and compare prefixes first, then, only for a secrets path inside the repository, run `git check-ignore -q` on `<secrets path>/.probe`. Exit code 0 continues, 1 stops, anything else stops. For the other output paths, the same check warns instead of stopping. Handle the case where the controller is not run from a git checkout (no repository root): treat every path as outside the repository.
- Write `tasks/write_attempt.yml` as specified under "The attempt record", with state `in_progress`, written from the resolved platform and hostname only. Write a small reusable task file for changing the attempt state (for example `tasks/set_attempt_state.yml`), since four other steps need it.

Checks: write a test playbook, `tests/prepare_paths.yml`, that runs the steps up to `write_attempt.yml` and covers at least: default paths outside the repository; a secrets path inside the repository and not ignored (must stop); inside and ignored (must continue); a symbolic link from outside into the repository (must be caught); an existing secrets directory with mode `0755` (must stop). Use temporary directories under `artifacts/` for the cases, and make the test clean up after itself.

### Phase 3: The transport

Follow the transport part of the Migration section:

- Change `raw_node_transport_incus_exec` to read the payload from `{{ raw_node_secrets_dir }}/{{ raw_node_hostname }}/raw-node-firstboot` and to write its run log to `{{ raw_node_logs_dir }}/{{ raw_node_hostname }}/incus_exec-run.log`, instead of `artifacts/<hostname>/`.
- Add `no_log: true` to the payload push and run tasks, and apply the masked-task rule so a failed payload run sets `raw_node_failure_reason` (step name, return code, log path), without output.
- The run log keeps the payload's output, since the payload's own output rules keep secrets out of it, but write it with mode `0600`.
- Set the ownership keys on launch, and rewrite `tasks/destroy.yml` so it works both in the build run and standalone (see Known gaps). It needs only the hostname and the project.
- Add `tasks/address.yml`, which looks the instance up and sets the IPv4 and IPv6 global addresses for `wait_phone_home.yml`. Reuse the address expression from `main.yml` rather than copying it, for example by moving the lookup into `address.yml` and including it from `main.yml`.
- Review the role's `defaults/main.yml` against the precedence decision: any value that must not be overridden by the play (in particular `raw_node_incus_allow_existing` is a safety setting, but it is meant to be overridable by the operator with `-e`, so decide carefully and explain the choice) goes in `vars/main.yml`. Do not move a value that an operator legitimately sets.
- Update the role's `README.md`.

Checks: `PATH="$PWD/tests/bin:$PATH" ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_test_destroy=true` passes. Extend `tests/bin/incus` as needed so it records `--config` keys and refuses to delete an instance without them, and add a case to the test showing that a pre-existing instance without the keys is neither adopted nor deleted. Nothing is written outside `artifacts/` during the test (check with `git status --ignored`).

### Phase 4: The build pipeline

- Write `build.yml` exactly as in the design, including the comment block, with `prepare_paths.yml` and `write_attempt.yml` before the block.
- Write `tasks/wait_phone_home.yml` for the transport source only, as the first release decisions say: if the entry has `reports_address: true` and the transport has `tasks/address.yml`, take the address from the transport, bounded by `raw_node_report_timeout` (600 in `vars/defaults.yml`). Otherwise fail with a message saying the phone-home receiver is not implemented yet. Write `reports/<hostname>/report.yml` and set `raw_node_report_*`. SSH host public keys: collect them through the transport if that is straightforward with `incus exec` (`/etc/ssh/ssh_host_*_key.pub`); if not, leave the field empty and note it.
- Write `tasks/write_confirmation.yml` as specified: the confirmation format from the strategy document, attempt state `confirmed`, the node's secrets directory deleted.
- Write `tasks/handle_failure.yml` in the order the design gives: failure record first, then destroy or quarantine with teardown in its own block, then delete secrets, then fail with the original error. Never copy `ansible_failed_result` whole into the record. Record `no_report` as the reason for a report timeout.
- Write the placeholders for `tasks/payload.yml` and `raw_node_validator` (see Known gaps). Each placeholder accepts a test-only override so the pipeline can be exercised: `payload.yml` copies `raw_node_test_payload_file` into the secrets directory when that variable is set, and the validator passes when `raw_node_test_skip_validation` is true. Both overrides are set only in tests and are named so nobody mistakes them for features.

Checks, using the stand-in Incus client, in a new test playbook `tests/build.yml` that wraps the pipeline with the test overrides:

- A successful run writes `records/<hostname>/attempt.yml` (state `confirmed`), `confirmation.yml` and `reports/<hostname>/report.yml` under `artifacts/`, and leaves no files in the node's secrets directory.
- A forced payload failure (a stand-in payload that exits non-zero) produces a failure record with a reason naming the step and return code and containing no output, state `destroyed`, no secrets left, and a non-zero exit whose message is the original failure.
- A forced teardown failure (make the stand-in client fail on `delete`) leaves state `quarantined`, with the teardown error added to the existing failure record.
- With the placeholders unmodified (no test overrides), `build.yml` fails inside the block on "not implemented yet", runs the rescue path, and leaves a failure record.
- Grep every file under `artifacts/` after these runs for the password hashes and the SSH key from the fixture. Only the stand-in payload's own staging copy may contain them, and it must be gone by the end of each run.

### Phase 5: Standalone destroy

- Write `destroy.yml` as specified under "Destroying a node": hostname only, platform from the attempt record or `-e target_platform`, registry loaded and validated, stop if `can_destroy` is false, transport teardown with `tasks_from: destroy`, attempt state `destroyed`, leftover secrets deleted, records kept.

Checks: build a node with `tests/build.yml`, then destroy it with `destroy.yml` (through a test wrapper that loads `tests/vars/output.yml`); destroy with the attempt record removed and `-e target_platform` given; destroy with neither, which must stop with a clear message; destroy an instance the controller did not create, which must refuse.

### Phase 6: Documents and session record

- Update `README.md`: status table, build order (priority 1 is `incus_container_default` on Debian 13; priority 2 is a Debian 13 VPS, which replaces `incus_container_cloud` as the next platform after it; keep the remaining steps after those two), layout, usage (`build.yml`, `validate.yml`, `destroy.yml`), registry path, and the operational notes listed at the end of the design's Migration section (records are operational state; where the secrets path is; backups and cloud sync of the home directory copy the secrets path and records; a second controller host starts with no secrets and no records).
- Create the next version of the two design documents the Migration section names, each by `git mv` of the current file to the new version number and then editing: `collapsable-strategy-for-a-raw-node-controller-v0.1.11.md` (entry point is `build.yml`; the payload and token are staged in the secrets path) and `1-the-platform-registry-v0.1.5.md` (registry path is `registry/base.yml`; no paths into the old role). Change only what the move requires, update the version and date in each metadata block, and add a Changes entry.
- Do not create v0.1.9 of the layout design. I will write that myself from your session record.
- Write a session record in `en/docs/sessions/`, named by the convention in that directory's README: create it at the start of the session as `$(date +%Y-%m-%d--%H-%M-%S)-session.md`, and keep adding to the same file as you go, so a session that stops early still leaves a record. By the end it holds: what was done in each phase; every place you departed from v0.1.8, with the reason; the outcome of each known gap default; anything you found that the design does not cover; which checks were run, and which still need a real Incus host; and open questions for me.

Final check: run every test playbook from the repository root, once more, in one go, and include the summary in the session record.

### Phase 7: Priority 1 on a real Incus host

This phase finishes the last item of the design's Migration section for the priority 1 node. It runs only if `incus` is on the path and `incus info` succeeds. If not, skip it and write the exact commands for me to run into the session record.

- **Isolation.** Do every real-host test in a dedicated Incus project, `uc-raw-node-test`, so nothing in my other projects can be touched. If the project does not exist, stop and ask before creating it; the command you will propose is `incus project create uc-raw-node-test -c features.images=false -c features.profiles=false`, which shares the default project's images and profiles. Pass `-e raw_node_incus_project=uc-raw-node-test` to every run, and never run `incus delete` outside that project.
- **Image.** Pass `-e raw_node_incus_image=images:debian/13` explicitly, so the test does not depend on the role default.
- **Transport test.** Run `tests/transport_incus_exec.yml` against real Incus with `raw_node_test_destroy=true`. Check that the instance gets the ownership keys, that the stand-in payload runs, that the log lands in `artifacts/logs/`, and that the instance is gone afterwards.
- **Pipeline test.** Run `tests/build.yml` with the test overrides. Check the attempt record, the report (real IPv4 and IPv6 addresses, and SSH host keys if Phase 4 collected them) and the confirmation, then run the standalone destroy test against the node it built.
- **Refusal test.** Launch a plain `images:debian/13` container in `uc-raw-node-test` yourself, without the ownership keys, using the fixture's hostname, and check that both the build and the destroy refuse to touch it. Then delete it by hand.
- **Clean up.** Leave the `uc-raw-node-test` project empty at the end, and say in the session record whether you created it.

This is not yet a raw node, because the payload is a placeholder: it shows that the controller can build, report, confirm and destroy a Debian 13 container safely. Record that limit in the session record, along with how long each step took on the real host (it informs `raw_node_report_timeout`).

### When to stop and ask

Stop and ask before going on if:

- A step in the design cannot be implemented as written without changing what the strategy or registry document defines.
- A known gap default turns out not to work.
- A check fails and the fix would change a step contract.
- You would need to delete or rewrite anything outside `roles/`, `tasks/`, `vars/`, `registry/`, `tests/`, the playbooks, `.gitignore`, `ansible.cfg`, `README.md`, your session record in `en/docs/sessions/` and the documents named in Phase 6.

## Changes

### From v0.1.2 to v0.1.3

- Named the sessions README by its path, `en/docs/sessions/README.md`, as its own item in Read first, since Claude Code does not know which directory the kickoff was pasted from.
- Moved the session record from `en/docs/dev/` to `en/docs/sessions/`, named by that directory's timestamp convention, and asked for it to be created at the start of the session and kept up to date.
- Added the session record to the files Claude Code may write without asking.
- Set the version in the metadata block, which still read 0.1.1.

### From v0.1.1 to v0.1.2

- Pointed Claude Code to the sessions README for how sessions are recorded.

### From v0.1.0 to v0.1.1

- Added the two priorities: a Debian 13 container on a local Incus server first, then a Debian 13 VPS, which is not built in this session but must not be ruled out by Incus-only choices.
- Added Phase 7, a real Incus host run on `images:debian/13` in a dedicated `uc-raw-node-test` project, as the acceptance test for priority 1, replacing the list of commands at the end of Phase 6.
- Described the transport's ownership marker as a rule every transport follows, so the VPS transport inherits it.
- Added the new build order to the README update in Phase 6.
