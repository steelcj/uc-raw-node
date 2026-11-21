# Raw Node Controller Layout Design

- **Version:** 0.1.10
- **Date:** 2026-11-21
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose and scope

This document decides how the uc-raw-node controller is laid out on disk and how its steps call each other. It covers the entry playbooks, the task files, which parts stay roles, where the controller writes its output, the contracts of the steps that touch a node, variable naming, and what the transports must guarantee to the controller. What the controller does (strategies, transports, registry, failure handling) is defined in *Collapse Strategy for a Raw Node Controller* v0.1.11 and *The Platform Registry* v0.1.5; this document does not change any of it.

The sequencing principle is to get the flow working end to end with the simplest mechanism, then promote a part to a role once it varies independently of the rest. Applied to the repository, that meant flattening the controller role into playbooks with task files, while the transport roles, which already vary independently, stay roles. That move is done (see Changes); this version records the layout as built, the decisions taken during the move, and the changes the code still has to catch up with.

## The mechanism problem

Ansible playbooks do not call other playbooks dynamically. The options for composing the controller are:

| Mechanism | Conditional dispatch? | Shared variables? | Use in uc-raw-node |
| :-- | :-- | :-- | :-- |
| `import_playbook` | No: resolved at parse time, and a `when` only filters the imported tasks | Yes, same run | Test wrappers only (see test wrappers) |
| Subprocess (`ansible-playbook other.yml`) | Yes | No: each run starts with a fresh context | Test scenario runners only, which need a separate exit code per scenario |
| `include_tasks` (task files) | Yes | Yes | Controller steps |
| `include_role` | Yes, the role name can be templated | Yes, plus the role's own defaults | Transports, and the validator |

The role name in `include_role` can be a variable, as in the module's own loop example <a id="cite-ansible-include-role"></a>[(Ansible Project, n.d.-a)](#ref-ansible-include-role). Dynamic dispatch on the transport therefore works with roles as well as with task files, and the choice between the two can be made on other grounds: whether the part has its own settings, its own tests, or a second consumer.

## Decision

- **Controller steps are task files,** because they are internal to one pipeline, have no consumer other than `build.yml`, `validate.yml` and `destroy.yml`, and gain nothing from a role wrapper. The tasks live in `tasks/`, the settings in `vars/defaults.yml`, and the base registry in `registry/base.yml`.
- **Transports stay roles,** because each has its own settings, its own test playbook and its own safety rules, and is chosen at run time by name. Adding a transport means writing a `raw_node_transport_<name>` role that meets the transport obligations below and listing it in `raw_node_known_transports`.
- **Controller defaults outrank transport defaults,** because `vars/defaults.yml` is loaded through play `vars_files`, which sits above role defaults. A value in a transport's `defaults/main.yml` is advisory and can be replaced by the play. A value the transport must keep, such as a safety setting, goes in the role's `vars/main.yml`, which outranks `vars_files` (see defaults and precedence).
- **The validator is a role** (`raw_node_validator`), because the orchestration controller may reuse it and the validation pipeline is meant to run identically wherever it is called.
- **Teardown and address lookup belong to the transport,** because only the transport knows how its platform names, finds and destroys an instance. A transport that supports destruction has `tasks/destroy.yml`, called with `tasks_from: destroy`, so the rescue path in `build.yml` and the standalone `destroy.yml` use the same code. A transport whose platform reports addresses has `tasks/address.yml`, called the same way by `wait_phone_home.yml`.
- **A transport deletes only what it can prove it created,** because a hostname is not proof of ownership: an earlier node, possibly confirmed and in use, can carry the same name. Ownership is proved two ways, depending on the context (see transport obligations). In a build run, only an instance that run launched may be deleted. In a standalone teardown, only an instance carrying the transport's ownership marker for that hostname may be deleted. Ownership is recorded on the platform itself, so it works from any controller host.
- **Every build writes an attempt record before it touches a platform,** because failure handling and `destroy.yml` both need to know what was attempted without the operator keeping the contract input around.
- **Output is split by purpose,** because files that later runs depend on must not sit next to files that are safe to delete. Records, reports and logs each have their own directory, and `artifacts/` is kept for development and testing only.
- **Sensitive files live outside the repository,** in a configurable `raw_node_secrets_path`, because the rendered payload carries contract values and the phone-home token, and a directory outside the repository cannot be committed by accident.

## Layout

```text
uc-raw-node/
├── ansible.cfg                         # roles_path = ./roles, needed by test playbooks in tests/
├── build.yml                           # Entry point: the full pipeline
├── validate.yml                        # Registry and input checks only, nothing is built
├── destroy.yml                         # Tear down a node by hostname
├── tasks/
│   ├── validate_registry.yml           # Loads and checks every registry layer and entry
│   ├── load_registry_layer.yml         # Loads one registry file
│   ├── load_input.yml                  # Collects and checks the contract input
│   ├── resolve_platform.yml            # Resolves target_platform and checks it can be used
│   ├── prepare_paths.yml               # Expands and creates the output paths, checks secrets permissions
│   ├── write_attempt.yml               # Writes the attempt record before anything is created
│   ├── set_attempt_state.yml           # Changes the attempt state, used by every later step
│   ├── payload.yml                     # Renders raw-node-firstboot into the secrets path (placeholder)
│   ├── wait_phone_home.yml             # Waits for the report, or asks the transport for the address
│   ├── write_confirmation.yml          # Writes confirmation.yml
│   └── handle_failure.yml              # Records the failure, then destroys or quarantines
├── templates/
│   └── raw-node-firstboot.j2           # Added with the real payload
├── vars/
│   └── defaults.yml                    # Root, registry files, input fields, known transports, paths, timeouts
├── registry/
│   ├── base.yml                        # Base platform registry
│   └── clients/
│       └── vishpala.yml                # Client layer (platforms: {}), opted into by appending it
├── roles/
│   ├── raw_node_transport_incus_exec/  # Transport for Incus instances without cloud-init
│   │   ├── defaults/main.yml           # Project, image, profiles, timeouts, client binary
│   │   ├── vars/main.yml               # Values the play must not override: ownership marker keys, raw_node_incus_allow_existing
│   │   └── tasks/
│   │       ├── main.yml                # Launch, deliver and run the payload
│   │       ├── address.yml             # Report the instance address and SSH host keys
│   │       └── destroy.yml             # Destroy an instance this transport can prove it created
│   └── raw_node_validator/             # Checks the RN-* clauses on the built node (placeholder)
├── tests/
│   ├── prepare_paths.yml               # Repository, ignore and permission checks
│   ├── transport_incus_exec.yml        # Transport, including the unmarked-instance case
│   ├── build.yml                       # Wraps build.yml with test overrides
│   ├── build_scenarios.yml             # Runs success, payload_failure, teardown_failure, placeholders
│   ├── destroy.yml                     # Wraps destroy.yml
│   ├── destroy_scenarios.yml           # Runs the four destroy cases
│   ├── tasks/                          # Per-case helpers for the runners
│   ├── vars/output.yml                 # Sets raw_node_root and points every output path into artifacts/
│   ├── fixtures/
│   └── bin/incus                       # Stand-in Incus client
├── records/                            # Attempt, failure and confirmation records, ignored by git
├── reports/                            # Address reports and validation results, ignored by git
├── logs/                               # Transport and payload logs, ignored by git
└── artifacts/                          # Development and test output only, ignored by git
```

The secrets path is outside the repository and does not appear in the tree.

### The repository root

Every repository-relative path is built from `raw_node_root`, which `vars/defaults.yml` sets to `"{{ playbook_dir }}"`. The entry playbooks live at the root, so this is the root for them. A test playbook in `tests/` has `tests/` as its `playbook_dir`, so `tests/vars/output.yml` sets `raw_node_root: "{{ playbook_dir }}/.."`. Test playbooks include task files as `../tasks/<file>.yml`, load `../vars/defaults.yml`, and are run from the repository root so that `ansible.cfg` and its `roles_path` apply.

## Output directories

### Purpose of each directory

| Directory | Variable | Holds | Safe to delete? |
| :-- | :-- | :-- | :-- |
| `records/<hostname>/` | `raw_node_records_path` | `attempt.yml`, `failure.yml`, `confirmation.yml` | No: `destroy.yml` and the orchestration controller read them |
| `reports/<hostname>/` | `raw_node_reports_path` | Address or phone-home report, validation results | Yes, once the node is confirmed or destroyed |
| `logs/<hostname>/` | `raw_node_logs_path` | Transport and payload logs, exit codes | Yes |
| `<secrets path>/<hostname>/` | `raw_node_secrets_path` | Rendered payload, strategy files carrying contract values, phone-home token | Deleted by the controller after use |
| `artifacts/` | None | Development and test output only | Yes |

The defaults in `vars/defaults.yml` are:

```yaml
raw_node_root: "{{ playbook_dir }}"
raw_node_records_path: "{{ raw_node_root }}/records"
raw_node_reports_path: "{{ raw_node_root }}/reports"
raw_node_logs_path: "{{ raw_node_root }}/logs"
raw_node_secrets_path: "~/.secrets/uc-raw-node"
```

Each can be overridden with `-e` or a client layer. A relative path is taken from `raw_node_root`, not from the directory the command was run in. The secrets default is a `uc-raw-node` subdirectory, so the controller's files do not mix with other tools' files in `~/.secrets/`.

`prepare_paths.yml` creates each node's records, reports and logs directories with mode `0700`. Records and reports are written with mode `0644`, logs and secrets with mode `0600`.

`artifacts/` is never written by `build.yml` or `destroy.yml` with the defaults. The test playbooks list `tests/vars/output.yml` after `vars/defaults.yml` in `vars_files`, and that file points every output path, including the secrets path, into `artifacts/`.

### Records are operational state

`records/` is not a debug convenience. `destroy.yml` reads the platform from `records/<hostname>/attempt.yml`, and the orchestration controller reads `confirmation.yml`. Deleting a node's records breaks `destroy.yml` for that node until `-e target_platform` is supplied, and removes the hand-off for a confirmed node.

Records are ignored by git, so they exist only on the controller host that built the node. On a fresh clone or a second workstation, `-e target_platform` is the only way to destroy a node. If several hosts must manage the same nodes, records need a shared location, which is deferred.

A confirmation is valid only while the attempt record beside it says `confirmed`. Records are kept when a node is destroyed, so `confirmation.yml` outlives the node it describes. The orchestration controller therefore reads `attempt.yml` first and takes `confirmation.yml` only when the state is `confirmed`.

### One attempt per hostname

The records directory holds one current attempt per hostname. When `write_attempt.yml` starts a new attempt for a hostname that already has records, it first moves the existing `attempt.yml`, `failure.yml` and `confirmation.yml` into `records/<hostname>/history/<started>/`, named by the earlier attempt's start time, so a stale failure or confirmation is never read as belonging to the new attempt, and the node's history is kept. Reports are overwritten, since they are safe to delete.

### Handling sensitive files

The rendered payload is the contract input turned into something that runs on the node. It carries all five contract fields (the hostname, the initial user name, both password hashes and the SSH public key) and the attempt's phone-home URL and one-time token. The token is the most sensitive item: the hashes and the public key are meant to be placed on the node, while the token is a secret, though short-lived and single-use.

- **Location.** All of this is written only under `<raw_node_secrets_path>/<hostname>/`. With the default path that is outside the repository.
- **Overridden paths.** The protection against accidental commits is a property of the default paths, not of the mechanism: `-e raw_node_secrets_path=./secrets` would put the payload inside the repository. `prepare_paths.yml` therefore checks the expanded secrets path in two separate steps, before it creates anything. The other output paths hold no secrets, so for them the same check only warns. Operators who choose custom paths inside the repository add them to their ignore rules.

  - **Inside the repository** is decided first, without git's ignore check: the secrets path and the repository root (`git rev-parse --show-toplevel`, run in `raw_node_root`) are both resolved with `realpath`, so a symbolic link into the repository is caught, and the path is inside if it starts with the root. A path outside the repository needs no further check. If `raw_node_root` is not a git checkout, or `git` is not installed, every path counts as outside the repository, and the run notes it.
  - **Ignored** is then checked with `git check-ignore -q` on a file path inside the secrets directory, such as `<secrets path>/.probe`, rather than on the directory itself. Exit code 0 means ignored and the run continues; 1 means not ignored and the run stops; 128 or any other code means the check failed, and the run also stops, since a check that could not run is not a pass.
- **Permissions.** `prepare_paths.yml` creates each missing directory of the secrets path one level at a time with mode `0700`, and every file is written with mode `0600`. If the secrets path or a node's directory already exists with any group or other permission bits, the run stops before anything is written. Existing parent directories above the secrets path, such as an existing `~/.secrets`, are left as they are.
- **Lifetime.** The payload and token are deleted after delivery, or once validation passes where the transport needs them until then. `handle_failure.yml` deletes them as well, after writing the failure record.
- **Path expansion.** Ansible does not expand `~` everywhere, so `prepare_paths.yml` expands every output path once with the `expanduser` filter, joins a relative result onto `raw_node_root`, and sets the expanded values under separate names for later steps.
- **Masked messages.** Tasks that refer to the secrets path carry `no_log: true`. Their results are judged by separate assertions without `no_log`, whose messages name the setting (`raw_node_secrets_path`) and the mode, never the path.
- **Records and reports hold public data only.** The attempt record, the confirmation (address, user name, sudo) and the report (addresses, SSH host public keys) are written from the resolved platform, the node's own report and the initial user name, never from the rest of the contract input or the payload.
- **Logs depend on two rules.** `logs/` holds the transport's output and the payload's runtime output, and the payload runs on the node, so keeping contract values out of `logs/` is a requirement on the code, not a property of the design. Tasks that read or deliver the payload use `no_log: true`, and transports must not echo the payload into their logs. The payload follows the output rules below. The threat these rules defend against is secrets left on disk and copied into backups.
- **Payload output rules.** `raw-node-firstboot` never prints a contract value or the token, including in error messages: a failed step reports which step failed and its exit code, not its arguments. The shipped script does not run under `set -x` or an equivalent trace mode. Commands that take secrets (`chpasswd -e`, the phone-home request) read them from a file or standard input rather than from command-line arguments. The phone-home request is not made in a verbose mode that prints headers or the request body.
- **Contract input files.** `raw-node-input.yml` carries the same values, without the token. The secrets path is a suitable place to keep input files, and the controller accepts an input file from anywhere through `-e @<path>`.

## The build playbook

```yaml
---
# Pipeline: validate registry, load input, resolve platform, prepare
# output paths, write the attempt record, then inside one block: render
# payload, deliver via transport, wait for report, validate contract,
# write confirmation.
# Any failure inside the block runs tasks/handle_failure.yml, which writes
# the failure record first, then destroys or quarantines the node.
# Failures before the block stop the run with nothing to clean up.

- name: Build a raw node
  hosts: localhost
  connection: local
  gather_facts: false

  vars_files:
    - vars/defaults.yml

  tasks:
    - name: Validate registry
      ansible.builtin.include_tasks: tasks/validate_registry.yml

    - name: Load and check contract input
      ansible.builtin.include_tasks: tasks/load_input.yml

    - name: Resolve platform
      ansible.builtin.include_tasks: tasks/resolve_platform.yml

    - name: Prepare output paths
      ansible.builtin.include_tasks: tasks/prepare_paths.yml

    - name: Write attempt record
      ansible.builtin.include_tasks: tasks/write_attempt.yml

    - name: Build, verify and confirm
      block:
        - name: Render payload
          ansible.builtin.include_tasks: tasks/payload.yml

        - name: Deliver via transport
          ansible.builtin.include_role:
            name: "raw_node_transport_{{ raw_node_platform.transport }}"

        - name: Wait for phone-home report
          ansible.builtin.include_tasks: tasks/wait_phone_home.yml

        - name: Validate contract
          ansible.builtin.include_role:
            name: raw_node_validator

        - name: Write confirmation
          ansible.builtin.include_tasks: tasks/write_confirmation.yml

      rescue:
        - name: Handle failure
          ansible.builtin.include_tasks: tasks/handle_failure.yml
```

Run it:

```sh
ansible-playbook build.yml -e @raw-node-input.yml -e target_platform=incus_container_default
```

Registry, input and platform checks run before anything is created, and everything that creates or touches a node runs inside one block whose rescue section acts on the entry's `can_destroy` value. Output paths are prepared after the checks, so a run that fails validation creates no directories.

`resolve_platform.yml` asserts that the transport is in `raw_node_known_transports` before the block starts. This matters for more than the error message: from ansible-core 2.21, errors raised by an include itself are treated as fatal rather than rescuable unless the include sets `rescuable` <a id="cite-ansible-include-role-devel"></a>[(Ansible Project, n.d.-b)](#ref-ansible-include-role-devel), so a missing transport role would skip the rescue section entirely. The controller is tested on ansible-core 2.21.6, so it runs under that change.

The comment block at the top of `build.yml` is the pipeline's summary for a reader. Because the steps are dynamic includes, `--list-tasks` shows only their names, so the comment is kept in step with the tasks whenever a step is added, removed or reordered.

`validate.yml` is the first three tasks of `build.yml` and nothing else.

## Step contracts

These are the steps whose behaviour a reader cannot infer from their names. Contracts marked as not yet in the code are decisions of this version that the implementation has still to follow (see first release decisions).

### Contract input

`load_input.yml` collects the five contract fields from extra vars (`-e @raw-node-input.yml`), which is how the commands in this document pass them. If `raw_node_input_file` is set, it reads that file instead; there is no default file, since a default path invites keeping contract input in the repository. Unknown fields produce a warning for file input only, because extra vars cannot be listed.

After the checks, it sets `raw_node_input`, a mapping of the five checked fields, and `raw_node_hostname`. Later steps read only these (see contract input and precedence).

### The attempt record

`write_attempt.yml` writes `records/<hostname>/attempt.yml` after the output paths are prepared and before the block starts, after moving any earlier attempt's records into history (not yet in the code). It holds `hostname`, `target_platform`, `strategy`, `transport`, `started`, `updated` (the time of the last state change) and `state`.

The states are:

| State | Meaning | Set by |
| :-- | :-- | :-- |
| `in_progress` | The build has started | `write_attempt.yml` |
| `confirmed` | The node passed validation and the confirmation is written | `write_confirmation.yml` |
| `failed` | Failure handling has started; a record left in this state means it did not finish | `handle_failure.yml` |
| `aborted` | The build failed before the transport created anything, so there was nothing to tear down (not yet in the code) | `handle_failure.yml` |
| `destroyed` | A node existed and was torn down | `handle_failure.yml`, `destroy.yml` |
| `quarantined` | A node exists in an unknown state and was left for the operator | `handle_failure.yml` |

`set_attempt_state.yml` reads the record from disk, sets `state` and `updated`, and writes it back. If the record is missing, it writes a new one from the hostname and platform without a start time, which happens for `destroy.yml -e target_platform` on a host that did not build the node.

The record contains no credentials: it is copied from the resolved platform and the hostname, never from the rest of the contract input.

### Waiting for the report

`wait_phone_home.yml` produces the node's address and SSH host keys for the validator, or fails.

- **Source.** If the entry has `reports_address: true` and `roles/raw_node_transport_<name>/tasks/address.yml` exists under `raw_node_root`, the address comes from the transport, called with `tasks_from: address`. Otherwise it comes from the phone-home receiver, matched by the attempt's one-time token. The lookup by path assumes transports live in the repository's `roles/`, which holds until roles are packaged as a collection.
- **Timeout.** The wait is bounded by `raw_node_report_timeout`, set in `vars/defaults.yml` (600 seconds). `wait_phone_home.yml` passes it to the transport as an include parameter, so a transport's defaults never read a controller variable (not yet in the code: the Incus transport's default currently reads it). On the real Incus host, with a cached Debian 13 image, the address was available about 6 seconds after launch, so 600 seconds is generous for containers. Bare metal installs and image deployments take much longer, so this is expected to become a per-entry registry field, defined in *The Platform Registry* when the first entry needs it.
- **Output.** On success, the step writes `reports/<hostname>/report.yml` with `hostname`, `source` (`transport` or `phone_home`), `received`, `ipv4`, `ipv6` and `ssh_host_keys`, and sets `raw_node_report_*` for the validator. The host key list is empty when the image has no SSH server, which is the case for the default Debian 13 container image until the payload installs one.
- **Failure.** On timeout, the step sets `raw_node_report_status: no_report` and fails with a message naming the timeout and the expected source, for example "no address report for web-01 from the incus_exec transport within 600 seconds". `handle_failure.yml` records the reason as `no_report`, with the message as detail. No `RN-*` clause was checked, so the record says so rather than naming a clause.

### Writing the confirmation

`write_confirmation.yml` writes `records/<hostname>/confirmation.yml` in the format the strategy document defines (`timestamp`, `ip`, `ip6`, `user`, `sudo`), keyed by hostname, with `ip` and `ip6` the first reported addresses (null if none) and `user` the initial user name from `raw_node_input`, the one contract field that is public. It sets the attempt state to `confirmed` and deletes the node's directory under the secrets path.

### Failure handling order

`handle_failure.yml` must never leave the operator without a record, even when the cleanup itself fails. It runs in this order:

- **Capture the failure.** Before anything else, copy the failed task's name and the reason, since nested rescue sections later overwrite `ansible_failed_task` and `ansible_failed_result`.
- **Write the failure record.** Write `records/<hostname>/failure.yml` with `hostname`, `time`, `attempt` (platform key, strategy, transport, start time), `platform` (the resolved registry entry), `failed_task`, `reason`, `detail`, `clause` and `action`, and set the attempt state to `failed`. `reason` is `raw_node_failure_reason` when it is set, a reason code such as `no_report` when a step set one, and otherwise the module's message (trimmed to 500 characters) and return code. `clause` is the `RN-*` clause that failed where one is known, "unknown" until the validator names clauses, and "none checked: no report was received" for `no_report`. The full failed result is never copied into the record.
- **Then destroy, quarantine or abort.** If the transport created nothing in this run, set the state to `aborted` and skip teardown (not yet in the code: the state currently ends as `destroyed`). Otherwise, if the entry's `can_destroy` is true, call the transport with `tasks_from: destroy` inside its own block, and on success set the state to `destroyed`. If that block fails, its rescue section adds `teardown_error` (the teardown task, its message, and the platform's error output trimmed to 300 characters) to the failure record and sets the state to `quarantined`, with an alert. If `can_destroy` is false, set the state to `quarantined` and alert. An instance the run adopted rather than created (`raw_node_incus_allow_existing=true`) is quarantined, since the transport refuses to delete it.
- **Then delete the node's secrets,** whatever the outcome of teardown.
- **Then end the run with the original failure.** The last task fails with "Build of `<hostname>` failed at `<task>`: `<reason>`", the attempt state and the path of the failure record, so the run exits non-zero and the first error is not hidden behind a teardown error.

The platform error output in `teardown_error` is the one place raw command output reaches a record. It is allowed because teardown commands carry no payload or contract values, and without it a quarantined node's record would say only that a command failed. The rule against raw output applies to tasks with `no_log`.

### Failure reasons from masked tasks

A task with `no_log: true` has its whole result replaced by a censored placeholder, and that includes `ansible_failed_result` in the rescue section. The tasks most likely to fail inside the block (delivering and running the payload) carry `no_log`, so a failure record built from `ansible_failed_result` alone would say only that output was hidden.

The rule is that a task with `no_log` whose failure the record must describe publishes its own reason, free of secrets:

- **Check, then fail with a safe message.** The `no_log` task registers its result and does not fail on its own (`failed_when: false`). The next task, which has no `no_log`, sets `raw_node_failure_reason` to a message built only from safe fields (the step name, the return code, the instance, the log path) and then fails with `ansible.builtin.fail` using that message.
- **No raw output in the reason.** The reason never includes the task's standard output or standard error, even trimmed.
- **Full output goes to `logs/`.** The transport writes the payload's output to `logs/<hostname>/` under the payload output rules, and the reason points to that file.

`no_report` is set through `raw_node_report_status`. A general mechanism for reason codes, such as a `raw_node_failure_code` beside `raw_node_failure_reason`, is deferred until the validator names clauses.

### Destroying a node

`destroy.yml` needs only the hostname:

```sh
ansible-playbook destroy.yml -e hostname=web-01
```

- **Inputs.** `hostname` is checked with the same rule as in the contract input. The platform comes from `records/<hostname>/attempt.yml`, or from `-e target_platform=<key>` if the attempt record is missing. If neither is there, the run stops and asks for `-e target_platform`. If both are there and disagree, the run stops rather than guessing which is right. The contract input is not needed and is not loaded.
- **Registry and paths.** The registry is loaded and validated as in `build.yml`, the entry is resolved from the platform key, and `prepare_paths.yml` runs for the expanded paths and the secrets checks. If `can_destroy` is false, the run stops with a message saying the platform cannot be destroyed by the controller.
- **Teardown.** The transport is called with `tasks_from: destroy` and `raw_node_destroy_standalone: true`, so it deletes only an instance carrying its ownership marker for the hostname and refuses any other. A missing instance counts as already gone.
- **Record.** On success the attempt state is set to `destroyed`, and the node's directory under the secrets path is deleted. Records are kept, so the history of the node survives its teardown.

`prepare_paths.yml` both checks and creates directories, so a `destroy.yml` that stops early leaves empty per-hostname directories behind. This is harmless; splitting the checks from the creation is deferred.

## Transport obligations

Every transport role meets these rules, whatever its platform. The Debian 13 VPS transport, the next one planned, inherits them rather than a new design.

- **Ownership marker.** When the transport creates an instance, it records on the platform that uc-raw-node created it and for which hostname. The Incus transport sets the user keys `user.uc-raw-node.created=true` and `user.uc-raw-node.hostname=<hostname>`; a cloud provider transport uses instance tags. The key names live in the role's `vars/main.yml`, so the play cannot change them.
- **Teardown in a build run.** With `raw_node_destroy_standalone` unset or false, teardown deletes only an instance this run launched and that carries the marker. It does nothing if this run launched nothing, and refuses an instance the run adopted. The facts that prove this (for Incus, `raw_node_incus_launched` and `raw_node_incus_adopted`) are set at the start of the transport and just before launch, not at the end, so a build that fails early can never fall back on the marker alone and delete an earlier node with the same hostname.
- **Standalone teardown.** With `raw_node_destroy_standalone: true`, which only `destroy.yml` sets, teardown deletes an instance carrying the marker for the hostname and refuses one without it.
- **No adoption by accident.** A transport refuses to deliver to an instance that already exists unless the operator allows it for the run (for Incus, `raw_node_incus_allow_existing`). That switch lives in the role's `vars/main.yml`, so a play-level source such as `vars_files` or inventory cannot turn adoption on for every run, while `-e` still can for one.
- **Output for the controller.** A transport hands its results back as `raw_node_transport_result` (from delivery) and `raw_node_transport_address` (from `address.yml`, with `found`, `ipv4`, `ipv6`, `ssh_host_keys` and `waited`), so the controller never reads a transport-specific variable. `address.yml` does not fail on timeout; the caller judges the result.
- **Secrets.** The transport reads the payload from `{{ raw_node_secrets_dir }}/{{ raw_node_hostname }}/`, writes its logs to `{{ raw_node_logs_dir }}/{{ raw_node_hostname }}/` with mode `0600`, and follows the masked-task rule for every task that touches the payload.

## First release decisions

The first release supports the `adopt` strategy with the `incus_exec` transport only, matching the build order in the strategy document. Its acceptance target is priority 1, a Debian 13 container on a local Incus server (`incus_container_default` with `images:debian/13`), and the next target is priority 2, a Debian 13 VPS.

- `payload.yml` renders the bare `raw-node-firstboot` script, which is the `adopt` payload format, into the secrets path. Until the `RN-*` clauses are pinned down, it is a placeholder that stops the build with "not implemented yet". Rendering for the other strategies is added as `tasks/strategy_<name>.yml`, included by name from the resolved strategy, when the first entry that needs it is built.
- `raw_node_validator` is a placeholder that stops the build in the same way.
- `wait_phone_home.yml` takes the address from the transport, since `incus_container_default` reports its address. The phone-home receiver, and with it the token, is not needed until the first entry without `reports_address`.
- `handle_failure.yml` follows the failure handling order above. Post-failure fallback is not implemented until the open question in the strategy document is settled.

The placeholders accept two test-only overrides so the pipeline can be exercised end to end: `raw_node_test_payload_file` (copied into the secrets directory as the payload) and `raw_node_test_skip_validation` (the validator passes with a notice). They are set only by the test wrappers and are not features.

The code does not yet follow these decisions of this version:

- The `aborted` state for a build that failed before anything was created.
- Moving an earlier attempt's records into `records/<hostname>/history/<started>/`.
- `wait_phone_home.yml` passing the timeout to the transport as an include parameter.

The order in which the remaining parts are built is a roadmap, not a design decision, and is kept in the README.

## Variables

### Naming

The repository uses the `raw_node_` namespace. Within it, a second prefix names the step that sets the variable:

| Prefix | Set by |
| :-- | :-- |
| `raw_node_registry_*` | `validate_registry.yml`, `load_registry_layer.yml` |
| `raw_node_input` | `load_input.yml` |
| `raw_node_hostname` | `load_input.yml`, and `destroy.yml` from `-e hostname`, since it loads no contract input |
| `raw_node_platform`, `raw_node_delivery_strategy` | `resolve_platform.yml` |
| `raw_node_*_dir` (expanded paths), `raw_node_paths_*` (working values) | `prepare_paths.yml` |
| `raw_node_attempt_*` | `write_attempt.yml`, `set_attempt_state.yml` |
| `raw_node_payload_*` | `payload.yml` |
| `raw_node_transport_result`, `raw_node_transport_address` | Any transport role, as its output for the controller |
| `raw_node_<transport>_*` | The transport role's own working values, for example `raw_node_incus_*` |
| `raw_node_report_*` | `wait_phone_home.yml` |
| `raw_node_validation_*` | `raw_node_validator` |
| `raw_node_failure_reason` | Any step inside the block that fails after a `no_log` task |
| Other `raw_node_failure_*` | `handle_failure.yml` |
| `raw_node_destroy_*`, including `raw_node_destroy_standalone` | `destroy.yml` only |
| `raw_node_test_*` | Test wrappers only |

Two names outside the namespace are operator inputs rather than step variables: `hostname` and `target_platform`. No step sets them, with one exception: `destroy.yml` sets `target_platform` from the attempt record when it was not given with `-e`.

The output path settings (`raw_node_records_path`, `raw_node_reports_path`, `raw_node_logs_path`, `raw_node_secrets_path`) come from `vars/defaults.yml`. Because a `set_fact` cannot override a value given with `-e`, `prepare_paths.yml` sets the expanded paths under separate names (`raw_node_records_dir`, `raw_node_reports_dir`, `raw_node_logs_dir`, `raw_node_secrets_dir`), and later steps read only those. Existing variable names that already work are not renamed just to fit the table.

### Isolation

Neither layout isolates variables by itself. A `set_fact` is visible to everything that runs later for the same host, wherever it was set, and role defaults and vars are also visible outside the role unless `private_role_vars` is enabled. Prefixing is what prevents collisions.

Nothing enforces the prefixes. The two kinds of mistake behave differently:

- **A typo** (`raw_node_platfrm` for `raw_node_platform`) is read as an undefined variable and fails loudly at run time.
- **A collision** (two steps setting `raw_node_payload_path` with different meanings) fails silently: the later value wins and the earlier step's consumers read the wrong thing.

A CI check makes the rule mechanical: list every variable set by `set_fact` or `register` in `tasks/`, `roles/` and the entry playbooks (`build.yml`, `validate.yml`, `destroy.yml`), and fail if one does not match a row in the table, or if the same name is set in a file the table does not list for its row. A name may therefore be set from several files only where its row lists them: `raw_node_hostname` (`load_input.yml` and `destroy.yml`), `raw_node_attempt_*` (`write_attempt.yml` and `set_attempt_state.yml`), and `raw_node_failure_reason`, which any step inside the block may set. The only unprefixed name the check accepts is `target_platform`, set by `destroy.yml`. The same check guards the secret-handling rules: it flags any task whose arguments refer to the secrets path, the payload or the token and that does not carry `no_log: true`, and any `set -x` in the payload template.

The trigger for writing it was around 15 to 20 variables set across the task files and roles. After the migration, 60 distinct names are set in `tasks/` and `roles/`, and 63 with the entry playbooks, well past the trigger, so the check is the next piece of work after the follow-ups above rather than a deferred item.

### Contract input and precedence

The contract input arrives as extra vars, which have the highest precedence of any variable source <a id="cite-ansible-variables"></a>[(Ansible Project, n.d.-c)](#ref-ansible-variables). A `set_fact` cannot override them, so a normalized value written back under the same name (for example a trimmed `ssh_public_key`) is silently ignored. `load_input.yml` therefore copies the checked fields into the `raw_node_input` mapping, under a name the input does not use, and later steps read only that mapping and `raw_node_hostname`.

### Defaults and precedence

`vars/defaults.yml` is loaded through `vars_files`, which puts its values at play level. In practice:

- They can be overridden with `-e`, which is how a client layer is added (`raw_node_registry_files`).
- They override the transport roles' own defaults if the names collide, which the naming rule above is meant to prevent. A transport's `defaults/main.yml` is therefore advisory.
- When a transport needs a value that the controller must not override, it puts that value in the role's `vars/main.yml`. Role vars take precedence over play `vars_files`, so the transport's value holds, and only `set_fact`, include parameters or `-e` can replace it <a id="cite-ansible-variables-role-vars"></a>[(Ansible Project, n.d.-c)](#ref-ansible-variables). Inventory `host_vars` are not an escape hatch here, because they rank below play `vars_files`. The Incus transport keeps its ownership marker keys and `raw_node_incus_allow_existing` there.

### Test wrappers

A test cannot wrap `build.yml` or `destroy.yml` with `import_playbook` and override their `vars_files` with play vars, since `vars_files` outranks play vars on the imported play. The wrappers in `tests/` therefore use two plays: the first loads `../vars/defaults.yml` and `vars/output.yml` and copies the output paths, `raw_node_root`, the registry files and the input file into `set_fact`, which outranks `vars_files` in the next play; the second is `import_playbook` of the unchanged entry playbook. The scenario runners call each wrapper as a separate `ansible-playbook` process, so each scenario has its own exit code.

## Behaviour to know about dynamic includes

- **Tags.** Tags on an `include_tasks` or `include_role` task apply to the include, not to the tasks inside it. To run part of the pipeline by tag, pass the tags with `apply:` as well as on the include <a id="cite-ansible-include-role-apply"></a>[(Ansible Project, n.d.-a)](#ref-ansible-include-role). `validate.yml` covers the most common partial run without tags.
- **Listing.** `--list-tasks` shows the include tasks but not what is inside them, because the files are only read at run time. The comment block at the top of `build.yml` is the readable summary instead.
- **Relative paths.** An include inside a task file resolves relative to that file first, so `validate_registry.yml` can keep including `load_registry_layer.yml` by bare name.
- **Assertion messages.** In ansible-core 2.21, `fail_msg` is templated even when the assertion passes, so a message that reads a field which exists only on failure must guard it with `default`.

## What is deferred, and when to revisit

| Deferred | Trigger to revisit |
| :-- | :-- |
| Controller task files as roles | A task file is used by a second playbook, or needs settings that should not live in the shared `vars/defaults.yml` |
| Strategy task files beyond `adopt` | The first registry entry with another strategy is built, which priority 2 is likely to be |
| Per-entry report timeout | The first entry whose nodes take longer than the default timeout to report |
| Phone-home receiver | The first entry without `reports_address` |
| Shared records location | More than one controller host has to manage the same nodes |
| Collection packaging | A second controller (such as uc-ventoy) or the orchestration controller needs these roles or task files without copying them; `wait_phone_home.yml`'s lookup of `address.yml` by path changes with it |
| Inventory and multi-node runs | More than one node has to be built per run |
| Post-failure fallback | The strategy document's open question on fallback is settled |
| A general reason code (`raw_node_failure_code`) | The validator names the first `RN-*` clause |
| Splitting checks from creation in `prepare_paths.yml` | Empty directories left by a stopped `destroy.yml` become a nuisance |
| Dropping `raw_node_input_file` | Nothing but the tests uses it, and the fixtures move to extra vars |

Promoting a task file to a role is mostly mechanical: the file becomes `roles/<name>/tasks/main.yml`, its settings move to `roles/<name>/defaults/main.yml`, and the include becomes an `include_role`. Two things do change: template and file lookups resolve against the role's own directories, so templates move with it, and its settings drop to role-default precedence.

## Changes

### From v0.1.9 to v0.1.10

- Corrected the count of variables set after the migration from 22 to 60 in `tasks/` and `roles/` (63 with the entry playbooks), counted by the document's own rule.
- Made the CI check scan the entry playbooks too, and allow a name to be set from several files only where its row in the naming table lists them, since `raw_node_hostname` and `raw_node_attempt_*` are legitimately set in two files each.
- Added `destroy.yml` as a setter of `raw_node_hostname`, widened its row to `raw_node_destroy_*`, and stated that `hostname` and `target_platform` are operator inputs that no step sets, except `destroy.yml` setting `target_platform` from the attempt record.

### From v0.1.8 to v0.1.9

- Recorded that the migration from the `raw_node_controller` role is complete (branch `layout-migration`, pull request 1), and removed the Migration section, as v0.1.8 required. The procedure and the documents it updated (strategy v0.1.11, registry v0.1.5, the README) are in the session record `en/docs/sessions/2026-11-21--11-06-57-session.md`, and the layout before the migration is tagged `v0.1.0`.
- Updated the scope to strategy v0.1.11 and registry v0.1.5, and the layout tree to the files as built, including `set_attempt_state.yml`, the transport's `vars/main.yml` and the test runners.
- Added `raw_node_root` as the base for every repository-relative path, kept `roles_path` in `ansible.cfg` for the test playbooks, and stated that relative output paths are taken from `raw_node_root`.
- Made ownership a decision: a transport deletes only what it can prove it created, by what the run launched in a build and by the platform's ownership marker in a standalone teardown. Added a Transport obligations section covering the marker, both teardown contexts, adoption, the transport's output for the controller and secrets.
- Added the `aborted` state for a build that failed before anything was created, the table of attempt states, `updated` in the attempt record, history for earlier attempts' records, and the rule that a confirmation is valid only while its attempt is `confirmed`. Listed which of these the code does not follow yet.
- Stated that contract input comes from extra vars into the `raw_node_input` mapping, with `raw_node_input_file` as an explicit alternative, and replaced the per-field `raw_node_input_*` names with the mapping in the naming table, along with `raw_node_delivery_strategy`, `raw_node_paths_*`, the transport output names, `raw_node_destroy_standalone` and `raw_node_test_*`.
- Gave the failure record its field names, the capture-first step, the 500-character message limit, `teardown_error` with platform error output trimmed to 300 characters, and quarantine for adopted instances. Gave the report its field names and noted the empty host key list for images without an SSH server.
- Specified `destroy.yml`'s handling of a missing platform and of a record that disagrees with `-e target_platform`, and that it runs `prepare_paths.yml`.
- Added the no-checkout case to the repository check, directory and file modes, and masked assertion messages.
- Added the test wrapper pattern, the `fail_msg` templating behaviour, the tested ansible-core version, and the Phase 7 timing for the report timeout.
- Moved the CI check for variable prefixes and secret handling out of the deferred table, since the count of variables set has passed its trigger, and added four deferred items found during the migration.
- Trimmed the Changes section to its two most recent entries, as v0.1.8 required; git history holds the rest.

## References

<a id="ref-ansible-include-role"></a>Ansible Project. (n.d.-a). *ansible.builtin.include_role module: Load and execute a role* (ansible-core 2.17). Ansible Documentation. https://docs.ansible.com/projects/ansible-core/2.17/collections/ansible/builtin/include_role_module.html
[Return to citation](#cite-ansible-include-role)

<a id="ref-ansible-include-role-devel"></a>Ansible Project. (n.d.-b). *ansible.builtin.include_role module: Load and execute a role* (ansible-core devel). Ansible Documentation. https://docs.ansible.com/ansible-core/devel/collections/ansible/builtin/include_role_module.html
[Return to citation](#cite-ansible-include-role-devel)

<a id="ref-ansible-variables"></a>Ansible Project. (n.d.-c). *Using variables: Variable precedence*. Ansible Documentation. https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html
[Return to citation](#cite-ansible-variables)
