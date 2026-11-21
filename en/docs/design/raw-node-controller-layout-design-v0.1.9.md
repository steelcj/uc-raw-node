# Raw Node Controller Layout Design

- **Version:** 0.1.8
- **Date:** 2026-11-21
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose and scope

This document decides how the uc-raw-node controller is laid out on disk and how its steps call each other. It covers the entry playbooks, the task files, which parts stay roles, where the controller writes its output, the contracts of the steps that touch a node, variable naming, and how to move from the current layout. What the controller does (strategies, transports, registry, failure handling) is defined in *Collapse Strategy for a Raw Node Controller* v0.1.10 and *The Platform Registry* v0.1.4; this document does not change any of it.

The sequencing principle is to get the flow working end to end with the simplest mechanism, then promote a part to a role once it varies independently of the rest. Applied to the current repository, that means flattening the controller role into a playbook with task files, while the transport roles, which already vary independently, stay roles.

## The mechanism problem

Ansible playbooks do not call other playbooks dynamically. The options for composing the controller are:

| Mechanism | Conditional dispatch? | Shared variables? | Use in uc-raw-node |
| :-- | :-- | :-- | :-- |
| `import_playbook` | No: resolved at parse time, and a `when` only filters the imported tasks | Yes, same run | Not used |
| Subprocess (`ansible-playbook other.yml`) | Yes | No: each run starts with a fresh context | Not used, it loses all accumulated state |
| `include_tasks` (task files) | Yes | Yes | Controller steps |
| `include_role` | Yes, the role name can be templated | Yes, plus the role's own defaults | Transports, and the validator if it is shared |

The role name in `include_role` can be a variable, as in the module's own loop example <a id="cite-ansible-include-role"></a>[(Ansible Project, n.d.-a)](#ref-ansible-include-role). Dynamic dispatch on the transport therefore works with roles as well as with task files, and the choice between the two can be made on other grounds: whether the part has its own settings, its own tests, or a second consumer.

## Decision

- **Controller steps become task files,** because they are internal to one pipeline, have no consumer other than `build.yml`, `validate.yml` and `destroy.yml`, and gain nothing from a role wrapper. `roles/raw_node_controller/` is removed. Its tasks move to `tasks/`, its defaults to `vars/defaults.yml`, and its base registry to `registry/base.yml`. `build.yml` replaces `tasks/main.yml` as the entry point.
- **Transports stay roles,** because each has its own settings, its own test playbook and its own safety rules, and is chosen at run time by name. `raw_node_transport_incus_exec` already has all three (for example `raw_node_incus_allow_existing` and the rule that it never deletes an instance it did not create). Adding a transport still means writing a `raw_node_transport_<name>` role and listing it in `raw_node_known_transports`.
- **Controller defaults outrank transport defaults,** because `vars/defaults.yml` is loaded through play `vars_files`, which sits above role defaults. This changes the relationship between the controller and every transport: a value in a transport's `defaults/main.yml` is advisory and can be replaced by the play. A value the transport must keep, such as a safety setting, goes in the role's `vars/main.yml`, which outranks `vars_files`. Every transport role is written with this in mind from the start (see defaults after the move).
- **The validator is a role** (`raw_node_validator`) if the orchestration controller may reuse it, because the validation pipeline is meant to run identically wherever it is called. If it will only ever run from `build.yml`, it can start as `tasks/validate_contract.yml` and be promoted later.
- **Teardown and address lookup belong to the transport,** because only the transport knows how its platform names, finds and destroys an instance. A transport role that supports destruction has `tasks/destroy.yml`, called with `tasks_from: destroy`, so the rescue path in `build.yml` and the standalone `destroy.yml` use the same code. A transport whose platform reports addresses has `tasks/address.yml`, called the same way by `wait_phone_home.yml`.
- **Every build writes an attempt record before it touches a platform,** because failure handling and `destroy.yml` both need to know what was attempted without the operator keeping the contract input around.
- **Output is split by purpose,** because files that later runs depend on must not sit next to files that are safe to delete. Records, reports and logs each have their own directory, and `artifacts/` is kept for development and testing only (see output directories).
- **Sensitive files live outside the repository,** in a configurable `raw_node_secrets_path`, because the rendered payload carries contract values and the phone-home token, and a directory outside the repository cannot be committed by accident.

## Layout

```text
uc-raw-node/
├── ansible.cfg
├── build.yml                           # Entry point: the full pipeline
├── validate.yml                        # Registry and input checks only, nothing is built
├── destroy.yml                         # Tear down a node by hostname
├── tasks/
│   ├── validate_registry.yml           # Loads and checks every registry layer and entry
│   ├── load_registry_layer.yml         # Loads one registry file
│   ├── load_input.yml                  # Loads and checks raw-node-input.yml
│   ├── resolve_platform.yml            # Resolves target_platform and checks it can be used
│   ├── prepare_paths.yml               # Expands and creates the output paths, checks secrets permissions
│   ├── write_attempt.yml               # Writes the attempt record before anything is created
│   ├── payload.yml                     # Renders raw-node-firstboot into the secrets path
│   ├── wait_phone_home.yml             # Waits for the report, or asks the transport for the address
│   ├── write_confirmation.yml          # Writes confirmation.yml
│   └── handle_failure.yml              # Records the failure, then destroys or quarantines
├── templates/
│   └── raw-node-firstboot.j2
├── vars/
│   └── defaults.yml                    # Registry files, input fields, known transports, paths, timeouts
├── registry/
│   ├── base.yml                        # Base platform registry
│   └── clients/
│       └── vishpala.yml                # Client layer
├── roles/
│   ├── raw_node_transport_incus_exec/  # Transport for Incus instances without cloud-init
│   │   └── tasks/
│   │       ├── main.yml                # Deliver and run the payload
│   │       ├── address.yml             # Report the instance address
│   │       └── destroy.yml             # Destroy an instance this transport created
│   └── raw_node_validator/             # Checks the RN-* clauses on the built node
├── tests/
│   ├── transport_incus_exec.yml
│   ├── vars/output.yml                 # Points every output path into artifacts/
│   ├── fixtures/
│   └── bin/incus
├── records/                            # Attempt, failure and confirmation records, ignored by git
├── reports/                            # Address reports and validation results, ignored by git
├── logs/                               # Transport and payload logs, ignored by git
└── artifacts/                          # Development and test output only, ignored by git
```

The secrets path is outside the repository and does not appear in the tree. `roles/` next to the playbooks is on Ansible's default role search path, so `ansible.cfg` does not need a `roles_path` entry for it.

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
raw_node_records_path: "{{ playbook_dir }}/records"
raw_node_reports_path: "{{ playbook_dir }}/reports"
raw_node_logs_path: "{{ playbook_dir }}/logs"
raw_node_secrets_path: "~/.secrets/uc-raw-node"
```

Each can be overridden with `-e` or a client layer. The secrets default is a `uc-raw-node` subdirectory, so the controller's files do not mix with other tools' files in `~/.secrets/`.

`artifacts/` is never written by `build.yml` or `destroy.yml` with the defaults. The test playbooks list `tests/vars/output.yml` after `vars/defaults.yml` in `vars_files`, and that file points every output path, including the secrets path, into `artifacts/`. A later `vars_files` entry wins over an earlier one, so the override works without `-e`.

### Records are operational state

`records/` is not a debug convenience. `destroy.yml` reads the platform from `records/<hostname>/attempt.yml`, and the orchestration controller reads `confirmation.yml`. Deleting a node's records breaks `destroy.yml` for that node until `-e target_platform` is supplied, and removes the hand-off for a confirmed node.

Records are ignored by git, so they exist only on the controller host that built the node. On a fresh clone or a second workstation, `-e target_platform` is the only way to destroy a node. If several hosts must manage the same nodes, records need a shared location, which is deferred.

### Handling sensitive files

The rendered payload is the contract input turned into something that runs on the node. It carries all five contract fields (the hostname, the initial user name, both password hashes and the SSH public key) and the attempt's phone-home URL and one-time token. The token is the most sensitive item: the hashes and the public key are meant to be placed on the node, while the token is a secret, though short-lived and single-use.

- **Location.** All of this is written only under `<raw_node_secrets_path>/<hostname>/`. With the default path that is outside the repository.
- **Overridden paths.** The protection against accidental commits is a property of the default paths, not of the mechanism: `-e raw_node_secrets_path=./secrets` would put the payload inside the repository. `prepare_paths.yml` therefore checks the expanded secrets path in two separate steps. The other output paths hold no secrets, so for them the same check only warns. Operators who choose custom paths inside the repository add them to their ignore rules.

  - **Inside the repository** is decided first, without git's ignore check: the secrets path and the repository root (`git rev-parse --show-toplevel`) are both resolved with `realpath`, so a symbolic link into the repository is caught, and the path is inside if it starts with the root. A path outside the repository needs no further check.
  - **Ignored** is then checked with `git check-ignore -q` on a file path inside the secrets directory, such as `<secrets path>/.probe`, rather than on the directory itself. The directory may not exist yet, and git cannot match a directory-only pattern such as `secrets/` against a path it does not know to be a directory. Exit code 0 means ignored and the run continues; 1 means not ignored and the run stops; 128 or any other code means the check failed, and the run also stops, since a check that could not run is not a pass.
- **Permissions.** `prepare_paths.yml` creates each missing directory of the secrets path one level at a time with mode `0700`, rather than letting parents be created with the default umask, and every file is written with mode `0600`. If the secrets path or a node's directory already exists with looser permissions, the run stops before anything is written. Existing parent directories above the secrets path, such as an existing `~/.secrets`, are left as they are.
- **Lifetime.** The payload and token are deleted after delivery, or once validation passes where the transport needs them until then. `handle_failure.yml` deletes them as well, after writing the failure record. Moving them out of the repository reduces the risk; it does not make them safe to keep.
- **Path expansion.** Ansible does not expand `~` everywhere, so `prepare_paths.yml` expands every output path once with the `expanduser` filter and sets the expanded values for later steps.
- **Records and reports hold public data only.** This is a property of the design: the attempt record, the confirmation (address, user name, sudo) and the report (addresses, SSH host public keys) are written from the resolved platform and the node's own report, never from the contract input or the payload.
- **Logs depend on two rules.** `logs/` holds the transport's output and the payload's runtime output, and the payload runs on the node, so keeping contract values out of `logs/` is a requirement on the code, not a property of the design. Tasks that read or deliver the payload use `no_log: true`, and transports must not echo the payload into their logs. The payload follows the output rules below. The threat these rules defend against is secrets left on disk and copied into backups; since `logs/` is ignored by git, committing them is not the risk.
- **Payload output rules.** `raw-node-firstboot` never prints a contract value or the token, including in error messages: a failed step reports which step failed and its exit code, not its arguments. The shipped script does not run under `set -x` or an equivalent trace mode. Commands that take secrets (`chpasswd -e`, the phone-home request) read them from a file or standard input rather than from command-line arguments, which keeps them out of process listings and out of any error output that repeats the command. The phone-home request is not made in a verbose mode that prints headers or the request body.
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

The structure follows the Ansible outline in v0.1.10: registry, input and platform checks run before anything is created, and everything that creates or touches a node runs inside one block whose rescue section acts on the entry's `can_destroy` value. Validation failures before the block stop the run with nothing to clean up. Output paths are prepared after the checks, so a run that fails validation creates no directories.

`resolve_platform.yml` asserts that the transport is in `raw_node_known_transports` before the block starts. This matters for more than the error message: from ansible-core 2.21, errors raised by an include itself are treated as fatal rather than rescuable unless the include sets `rescuable` <a id="cite-ansible-include-role-devel"></a>[(Ansible Project, n.d.-b)](#ref-ansible-include-role-devel), so a missing transport role would skip the rescue section entirely.

The comment block at the top of `build.yml` is the pipeline's summary for a reader. Because the steps are dynamic includes, `--list-tasks` shows only their names, so the comment is kept in step with the tasks whenever a step is added, removed or reordered.

`validate.yml` is the first three tasks of `build.yml` and nothing else.

## Step contracts

These are the steps whose behaviour a reader cannot infer from their names. The contracts are provisional until each step is built, and the implementation records any change here.

### The attempt record

`write_attempt.yml` writes `records/<hostname>/attempt.yml` after the output paths are prepared and before the block starts. It holds the hostname, the `target_platform` key, the resolved strategy and transport, the start time and the attempt's state (`in_progress` at first). Later steps update the state: `confirmed` from `write_confirmation.yml`, and `failed`, `destroyed` or `quarantined` from `handle_failure.yml`.

The record contains no credentials: it is copied from the resolved platform and the hostname, never from the rest of the contract input.

### Waiting for the report

`wait_phone_home.yml` produces the node's address and SSH host keys for the validator, or fails.

- **Source.** If the entry has `reports_address: true` and the transport has `tasks/address.yml`, the address comes from the transport (for `incus_exec`, from Incus). Otherwise it comes from the phone-home receiver, matched by the attempt's one-time token. In both cases the step writes the same evidence.
- **Timeout.** The wait is bounded by `raw_node_report_timeout`, set in `vars/defaults.yml`, provisionally 600 seconds. Bare metal installs and image deployments take much longer than containers, so this is expected to become a per-entry registry field. That field is defined in *The Platform Registry* when the first entry needs it, not here.
- **Output.** On success, the step writes `reports/<hostname>/report.yml` with the address (IPv4 and IPv6), the SSH host public keys, the source (`transport` or `phone_home`) and the time received, and sets `raw_node_report_*` for the validator.
- **Failure.** On timeout, the step fails with a message naming the timeout and the expected source, for example "no phone-home report for web-01 within 600 seconds". `handle_failure.yml` receives this task as `ansible_failed_task` and records the reason as `no_report`. No `RN-*` clause was checked, so the record says so rather than naming a clause.

### Writing the confirmation

`write_confirmation.yml` writes `records/<hostname>/confirmation.yml` in the format the strategy document defines (timestamp, ip, ip6, user, sudo), sets the attempt state to `confirmed`, and deletes the node's directory under the secrets path. The confirmation is a record rather than a report, because it is the hand-off to the orchestration controller and must not be cleaned up with the reports.

### Failure handling order

`handle_failure.yml` must never leave the operator without a record, even when the cleanup itself fails (for example, the Incus daemon is unreachable or a provider API times out). It runs in this order:

- **Write the failure record first.** Before any teardown is attempted, write `records/<hostname>/failure.yml` with the attempt, the registry entry, the failed task's name and the reason for the failure (`ansible_failed_task` and `ansible_failed_result` are available in the rescue section, but the full result is never copied into the record), the `RN-*` clause that failed where one is known, and the action about to be taken. Set the attempt record's state to `failed`. The reason comes from `raw_node_failure_reason` when it is set, and from the module's message and return code otherwise (see failure reasons from masked tasks).
- **Then destroy or quarantine.** If the entry's `can_destroy` is true, call the transport with `tasks_from: destroy` inside its own block, and on success set the attempt state to `destroyed`. If that block fails, its rescue section adds the teardown error to the failure record and sets the state to `quarantined`. If `can_destroy` is false, set the state to `quarantined` and alert.
- **Then delete the node's secrets.** The payload and token are removed from the secrets path, whatever the outcome of teardown.
- **Then end the run with the original failure.** The last task fails explicitly, naming the original failure and pointing to the record, so the run exits non-zero and the first error is not hidden behind a teardown error.

A teardown failure is therefore always a second entry in a record that already exists, never the only trace of what happened.

### Failure reasons from masked tasks

A task with `no_log: true` has its whole result replaced by a censored placeholder, and that includes `ansible_failed_result` in the rescue section. The tasks most likely to fail inside the block (delivering and running the payload) are exactly the ones that carry `no_log`, so a failure record built from `ansible_failed_result` alone would say only that output was hidden.

The rule is that a task with `no_log` whose failure the record must describe publishes its own reason, free of secrets:

- **Check, then fail with a safe message.** The `no_log` task registers its result and does not fail on its own (`failed_when: false`). The next task, which has no `no_log`, sets `raw_node_failure_reason` to a message built only from safe fields (the step name, the return code, the payload's own step marker) and then fails with `ansible.builtin.fail` using that message.
- **No raw output in the reason.** The reason never includes the task's standard output or standard error, even trimmed, because the payload's output rules are a requirement that a bug could break.
- **Full output goes to `logs/`.** Where the operator needs more detail, the transport writes the payload's output to `logs/<hostname>/` under the payload output rules, and the reason points to that file.

`handle_failure.yml` prefers `raw_node_failure_reason` and falls back to the module's message and return code for tasks without `no_log`, whose results are not masked.

### Destroying a node

`destroy.yml` needs only the hostname:

```sh
ansible-playbook destroy.yml -e hostname=web-01
```

- **Inputs.** `hostname` is checked with the same rule as in the contract input. The platform comes from `records/<hostname>/attempt.yml`. If the attempt record is missing (for example, on a different controller host, or after the records were deleted), `-e target_platform=<key>` supplies it instead. The full contract input is not needed and is not loaded.
- **Registry.** The registry is loaded and validated as in `build.yml`, and the entry is resolved from the platform key. If `can_destroy` is false, the run stops with a message saying the platform cannot be destroyed by the controller.
- **Teardown.** The transport is called with `tasks_from: destroy`. The transport's own safety rules still apply: `raw_node_transport_incus_exec` refuses to delete an instance it did not create.
- **Record.** On success the attempt record's state is set to `destroyed`, and any of the node's files left under the secrets path are deleted. Records are kept, so the history of the node survives its teardown.

## First release decisions

The first release supports the `adopt` strategy with the `incus_exec` transport only, matching the build order in the strategy document. In that scope:

- `payload.yml` renders the bare `raw-node-firstboot` script, which is the `adopt` payload format, into the secrets path. Rendering for the other strategies (cloud-config user-data, answer files, image manifests) is added as `tasks/strategy_<name>.yml`, included by name from the resolved strategy, when the first entry that needs it is built.
- `wait_phone_home.yml` takes the address from the transport, since `incus_container_default` reports its address. The phone-home receiver, and with it the token, is not needed until the first entry without `reports_address`.
- `handle_failure.yml` follows the failure handling order above. Post-failure fallback is not implemented until the open question in the strategy document is settled.

The order in which the remaining parts are built is a roadmap, not a design decision, and is kept in the README.

## Variables

### Naming

The repository already uses the `raw_node_` namespace (`raw_node_registry_files`, `raw_node_known_transports`, `raw_node_test_destroy`, `raw_node_incus_allow_existing`). That namespace stays. Within it, a second prefix names the step that sets the variable:

| Prefix | Set by |
| :-- | :-- |
| `raw_node_registry_*` | `validate_registry.yml`, `load_registry_layer.yml` |
| `raw_node_input_*` | `load_input.yml` |
| `raw_node_platform`, `raw_node_strategy` | `resolve_platform.yml` |
| `raw_node_*_path` (expanded) | `prepare_paths.yml` |
| `raw_node_attempt_*` | `write_attempt.yml` |
| `raw_node_payload_*` | `payload.yml` |
| `raw_node_<transport>_*` | The transport role, for example `raw_node_incus_*` |
| `raw_node_report_*` | `wait_phone_home.yml` |
| `raw_node_validation_*` | `raw_node_validator` |
| `raw_node_failure_reason` | Any step inside the block that fails after a `no_log` task |
| Other `raw_node_failure_*` | `handle_failure.yml` |

The output path settings (`raw_node_records_path`, `raw_node_reports_path`, `raw_node_logs_path`, `raw_node_secrets_path`) come from `vars/defaults.yml`. Because a `set_fact` cannot override a value given with `-e`, `prepare_paths.yml` sets the expanded paths under separate names (for example `raw_node_secrets_dir`), and later steps read only those. Existing variable names that already work are not renamed just to fit the table; the table governs new variables.

### Isolation

Neither layout isolates variables by itself. A `set_fact` is visible to everything that runs later for the same host, wherever it was set, and role defaults and vars are also visible outside the role unless `private_role_vars` is enabled. Prefixing is what prevents collisions, in this layout and in a role-based one.

Nothing enforces the prefixes. The two kinds of mistake behave differently:

- **A typo** (`raw_node_platfrm` for `raw_node_platform`) is read as an undefined variable and fails loudly at run time.
- **A collision** (two steps setting `raw_node_payload_path` with different meanings) fails silently: the later value wins and the earlier step's consumers read the wrong thing.

A CI check can make the rule mechanical: list every variable set by `set_fact` or `register` in `tasks/` and `roles/`, and fail if one does not match a prefix in the table, or if the same name is set in more than one file. `raw_node_failure_reason` is the one name the table allows to be set from several files. The same check guards the secret-handling rules, which are also conventions that fail invisibly: it flags any task whose arguments refer to the secrets path, the payload or the token and that does not carry `no_log: true`, and any `set -x` in the payload template. It should be written before it is needed, since a silent collision is only noticed after it has done damage. The trigger is around 15 to 20 variables set across the task files and roles, which is about as many as one person can track by memory, or a second author joining, whichever comes first.

### Contract input and precedence

The contract input arrives as extra vars (`-e @raw-node-input.yml`), which have the highest precedence of any variable source <a id="cite-ansible-variables"></a>[(Ansible Project, n.d.-c)](#ref-ansible-variables). A `set_fact` cannot override them, so a normalized value written back under the same name (for example a trimmed `ssh_public_key`) is silently ignored. `load_input.yml` therefore copies each checked field into a `raw_node_input_*` variable, and later steps read only those.

### Defaults after the move

This is the detail behind the decision that controller defaults outrank transport defaults. Moving `roles/raw_node_controller/defaults/main.yml` to `vars/defaults.yml` loaded through `vars_files` raises those values from the lowest precedence to play level. In practice:

- They can still be overridden with `-e`, which is how a client layer is added today (`raw_node_registry_files`).
- They override the transport roles' own defaults if the names collide, which the naming rule above is meant to prevent. A transport's `defaults/main.yml` is therefore advisory: a value there can be replaced by the play.
- When a transport needs a value that the controller must not override, such as a safety setting, it puts that value in the role's `vars/main.yml` instead. Role vars take precedence over play `vars_files`, so the transport's value holds, and only `set_fact`, include parameters or `-e` can replace it <a id="cite-ansible-variables-role-vars"></a>[(Ansible Project, n.d.-c)](#ref-ansible-variables). Inventory `host_vars` are not an escape hatch here, because they rank below play `vars_files`.
- Paths that were relative to the role, such as the base registry, are written relative to the playbook, for example `"{{ playbook_dir }}/registry/base.yml"`.

## Behaviour to know about dynamic includes

- **Tags.** Tags on an `include_tasks` or `include_role` task apply to the include, not to the tasks inside it. To run part of the pipeline by tag, pass the tags with `apply:` as well as on the include <a id="cite-ansible-include-role-apply"></a>[(Ansible Project, n.d.-a)](#ref-ansible-include-role). `validate.yml` covers the most common partial run without tags.
- **Listing.** `--list-tasks` shows the include tasks but not what is inside them, because the files are only read at run time. The comment block at the top of `build.yml` is the readable summary instead.
- **Relative paths.** An include inside a task file resolves relative to that file first, so `validate_registry.yml` can keep including `load_registry_layer.yml` by bare name.

## Migration from the current layout

This section is a one-time procedure. Once the move is done and the documents below are updated, it is removed in the next version, the Changes section records that it was completed, and the Changes section is trimmed to its two most recent entries, with git history holding the rest. This rule is local to this document for now; when the document conventions under development in uc-automa, uc-contracts, uc-cfap and uc-processes define one, that rule replaces it.

- Create `build.yml`, `validate.yml` and `destroy.yml` as above.
- Move `validate_registry.yml`, `load_registry_layer.yml`, `load_input.yml` and `resolve_platform.yml` from `roles/raw_node_controller/tasks/` to `tasks/`, unchanged except for paths.
- Move `roles/raw_node_controller/defaults/main.yml` to `vars/defaults.yml`, make its paths relative to `playbook_dir`, and add the output path settings.
- Move `roles/raw_node_controller/files/registry.yml` to `registry/base.yml`, and update the default for `raw_node_registry_files`.
- Remove `roles/raw_node_controller/`.
- Split any teardown logic in `raw_node_transport_incus_exec` into its `tasks/destroy.yml`, and add `tasks/address.yml`.
- Change `raw_node_transport_incus_exec` to write its output to the logs path instead of `artifacts/<hostname>/`, and to read the payload from the secrets path.
- Add `records/`, `reports/` and `logs/` to `.gitignore`, keeping `artifacts/`.
- Add `tests/vars/output.yml`, and list it after `vars/defaults.yml` in the test playbooks, so tests keep writing only into `artifacts/`.
- Update `tests/transport_incus_exec.yml` wherever it reaches into `raw_node_controller` (with `include_role` and `tasks_from`, or with paths into the role), so that it uses the files in `tasks/`.
- Run `validate.yml` against `tests/fixtures/raw-node-input.yml`, then run the transport test with the stand-in Incus client and on a real Incus host.

Documents that need updating once the move is made:

- *Collapse Strategy for a Raw Node Controller*: the Ansible implementation pattern names `roles/raw_node_controller/tasks/main.yml` as the entry point, and the credential exposure section should name the secrets path as where the payload and token are staged.
- *The Platform Registry*: any paths that point to `roles/raw_node_controller/files/registry.yml` or to the role's tasks.
- The README, separately. Its operational notes need to say that `records/` is operational state that `destroy.yml` depends on, and where the secrets path is. They also need to say that the secrets path and `records/` sit under the controller host's home directory by default, so any backup or cloud sync of that directory copies them to other devices, which the controller cannot prevent. And that on a second controller host the secrets path starts empty, which is harmless because tokens are single-use, but records are not shared either (see the deferred shared records location).

## What is deferred, and when to revisit

| Deferred | Trigger to revisit |
| :-- | :-- |
| Controller task files as roles | A task file is used by a second playbook, or needs settings that should not live in the shared `vars/defaults.yml` |
| Strategy task files beyond `adopt` | The first registry entry with another strategy is built |
| Per-entry report timeout | The first entry whose nodes take longer than the default timeout to report |
| Phone-home receiver | The first entry without `reports_address` |
| Shared records location | More than one controller host has to manage the same nodes |
| Collection packaging | A second controller (such as uc-ventoy) or the orchestration controller needs these roles or task files without copying them |
| Inventory and multi-node runs | More than one node has to be built per run |
| Post-failure fallback | The strategy document's open question on fallback is settled |
| CI check for variable prefixes and secret handling (`no_log` on secret-handling tasks, no trace mode in the payload) | Around 15 to 20 variables set across task files and roles, the first transport after `incus_exec`, or a second author joining, whichever comes first |

Promoting a task file to a role is mostly mechanical: the file becomes `roles/<name>/tasks/main.yml`, its settings move to `roles/<name>/defaults/main.yml`, and the include becomes an `include_role`. Two things do change: template and file lookups resolve against the role's own directories, so templates move with it, and its settings drop to role-default precedence.

## Changes

### From v0.1.7 to v0.1.8

- Spelled out the secrets path check as two steps: inside the repository by comparing resolved paths, then ignored by `git check-ignore -q` on a file path inside the directory, with exit code 1 and any error code both stopping the run.
- Replaced the reference to sat-doc-automa, which is being retired, with a concrete trimming rule (keep the two most recent entries), to be replaced by the rule in the new document conventions once they define one.

### From v0.1.6 to v0.1.7

- Resolved the conflict between `no_log` and the failure record: a `no_log` task's result is masked in the rescue section, so such tasks now publish a secret-free `raw_node_failure_reason` before failing, and `handle_failure.yml` prefers it.
- Separated what is guaranteed by design (records and reports hold public data only) from what is a requirement on the code (logs stay free of contract values), and named the threat the logs rule defends against: secrets left on disk and in backups.
- Added payload output rules: no contract values or token in output or error messages, no trace mode, secrets passed by file or standard input, no verbose phone-home request.
- Stated that the accidental-commit protection belongs to the default paths, and made `prepare_paths.yml` stop when the secrets path is inside the repository and not ignored by git.
- Made `prepare_paths.yml` create missing secrets directories one level at a time with mode `0700`.
- Extended the deferred CI check to cover secret handling, and added the first transport after `incus_exec` to its triggers.
- Added backups, cloud sync and second controller hosts to the README's operational notes in the documents to update.

### From v0.1.5 to v0.1.6

- Split the controller's output by purpose into `records/`, `reports/` and `logs/`, each with a configurable path, and kept `artifacts/` for development and testing only, with tests redirected there through `tests/vars/output.yml`.
- Added the configurable `raw_node_secrets_path` (default `~/.secrets/uc-raw-node`) outside the repository for the rendered payload, strategy files carrying contract values and the phone-home token, with permission checks, deletion after use, `no_log` and a rule that no other directory holds contract values.
- Stated that `records/` is operational state that `destroy.yml` and the orchestration controller depend on, and that records exist only on the controller host that wrote them.
- Added `prepare_paths.yml` to the layout and the build playbook, and a contract for writing the confirmation.
- Added deleting the node's secrets to the failure handling order and to `destroy.yml`, and limited what the failure record keeps from the failed result.
- Added a shared records location to the deferred list, the README's operational note to the documents to update, and the Changes trimming rule to the migration section.

### From v0.1.4 to v0.1.5

- Renamed the document from *The Mechanism Problem: Controller Layout for uc-raw-node* to *Raw Node Controller Layout Design*, to match the other design documents. "The mechanism problem" remains the heading of the section comparing the composition mechanisms.
- Gave each bullet in the Decision section its rationale, so the section can be read on its own.
- Promoted the precedence shift (controller defaults outrank transport defaults) to a decision, with a pointer to the detail.
- Added address lookup to the transport role, alongside teardown, and the attempt record as a decision.
- Added a Step contracts section with provisional contracts for the attempt record, waiting for the report (source, timeout, output, failure) and destroying a node (minimum inputs: the hostname, with the platform read from the attempt record), and moved the failure handling order into it.
- Added `write_attempt.yml` to the layout and the build playbook, and the transport's `address.yml` and `destroy.yml` to the layout.
- Renamed First release scope to First release decisions, and stated that build order belongs in the README.
- Marked the migration section as a one-time procedure to be removed once completed.
- Changed the CI check trigger from a collision being found to a variable count, or a second author, whichever comes first, and added the per-entry timeout and phone-home receiver to the deferred list.

### From v0.1.3 to v0.1.4

- Added a pipeline comment block at the top of `build.yml`, since `--list-tasks` cannot show what the dynamic includes do.
- Added the failure handling order: write the failure record first, then destroy or quarantine with teardown in its own block, then end the run with the original failure.
- Stated that nothing enforces the variable prefixes, distinguished loud typos from silent collisions, and added a CI check to the deferred list.
- Stated that a transport's role defaults are advisory once controller defaults load through `vars_files`, and that values the controller must not override go in the role's `vars/main.yml`.

### From v0.1.2 to v0.1.3

- Rewrote the document as a standalone design record: added the metadata block and the purpose and scope section, and removed the conversational opening.
- Changed the decision from "one playbook with task files" to a hybrid based on the current repository: the controller role is flattened into task files, and transports (and the validator, if shared) stay roles dispatched with `include_role`.
- Added `include_role` to the mechanism table, and corrected the `import_playbook` entry.
- Restored the block and rescue structure from the strategy document in `build.yml`, and added `wait_phone_home.yml`, `handle_failure.yml` and the `templates/` directory.
- Moved teardown into each transport role, shared by the rescue path and `destroy.yml`.
- Kept the existing `raw_node_` variable namespace, with a step prefix inside it, instead of introducing unnamespaced prefixes.
- Corrected the statement that roles isolate variables, and added the extra vars precedence issue for contract input and the precedence change for the moved defaults.
- Added the behaviour of tags, task listing and relative paths with dynamic includes, and the ansible-core 2.21 change to include errors.
- Added the first release scope, the migration steps and the list of documents to update.
- Fixed the YAML indentation and the layout tree, and replaced em dashes with commas.

## References

<a id="ref-ansible-include-role"></a>Ansible Project. (n.d.-a). *ansible.builtin.include_role module: Load and execute a role* (ansible-core 2.17). Ansible Documentation. https://docs.ansible.com/projects/ansible-core/2.17/collections/ansible/builtin/include_role_module.html
[Return to citation](#cite-ansible-include-role)

<a id="ref-ansible-include-role-devel"></a>Ansible Project. (n.d.-b). *ansible.builtin.include_role module: Load and execute a role* (ansible-core devel). Ansible Documentation. https://docs.ansible.com/ansible-core/devel/collections/ansible/builtin/include_role_module.html
[Return to citation](#cite-ansible-include-role-devel)

<a id="ref-ansible-variables"></a>Ansible Project. (n.d.-c). *Using variables: Variable precedence*. Ansible Documentation. https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html
[Return to citation](#cite-ansible-variables)
