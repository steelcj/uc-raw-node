# uc-raw-node

uc-raw-node is the raw node controller. It takes a short contract input file and a target platform, builds a node on that platform that meets the raw node contract (the `RN-*` clauses), and writes `confirmation.yml` so the orchestration controller can take over.

It does one job only. Discovery, onboarding, normalization and customization belong to the orchestration controller, and infrastructure-as-code tools such as Terraform, OpenTofu or Pulumi call uc-raw-node from outside rather than living inside it.

- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Status

The controller pipeline is in place: `build.yml` runs end to end, with the attempt record, the address report, the confirmation, failure handling and `destroy.yml`, and the Incus transport is tested. The payload and the validator are placeholders that stop the build with "not implemented yet", so the controller cannot build a complete raw node yet.

| Part | Status |
| :-- | :-- |
| Platform registry and `validate_registry.yml` | Done, tested |
| Contract input checking (`load_input.yml`) | Done, tested |
| Output paths, secrets checks (`prepare_paths.yml`) and attempt record | Done, tested |
| `raw_node_transport_incus_exec`, with ownership marker, `address.yml` and `destroy.yml` | Done, tested with a stand-in Incus client; real Incus host run: see the latest session record |
| Address report (`wait_phone_home.yml`, transport source) | Done, tested |
| Confirmation and failure handling | Done, tested with a stand-in Incus client |
| Standalone teardown (`destroy.yml`) | Done, tested with a stand-in Incus client |
| `payload.yml` (renders `raw-node-firstboot`) | Placeholder: fails "not implemented yet" |
| `raw_node_validator` | Placeholder: fails "not implemented yet" |
| Phone-home receiver | Not started |
| Other transports (`ssh`, `incus`, provider APIs, `ventoy_usb`) | Not started |

Tests can get past the placeholders with two test-only overrides, `raw_node_test_payload_file` and `raw_node_test_skip_validation`, which only `tests/build.yml` sets. A node built that way is not a raw node.

## How it works

The controller collapses many platforms into a small number of moving parts:

- **One payload.** Every node is set up by the same script, `raw-node-firstboot`, which creates the initial user, installs the SSH key, sets the root password hash, applies the baseline nftables ruleset and reports back. The `RN-*` clauses are implemented once, there.
- **Four strategies.** A strategy decides how the payload is packaged: `cloud_init` (cloud-config user-data), `installer` (Preseed, Kickstart or Subiquity autoinstall), `image` (baked into a disk image) or `adopt` (pushed over a channel that already exists, such as SSH or `incus exec`).
- **Transports.** A transport is a small role that delivers the packaged payload to the platform, for example `raw_node_transport_incus_exec`. This is the pluggable part.
- **A platform registry.** Plain YAML that says, for each platform, which strategy and transport to use and what the platform can do (whether a failed node can be destroyed, whether it reports its address, whether the firewall clause applies). Adding a platform on an existing transport is a data change only.
- **One validator.** The contract is checked the same way no matter how the node was built.

The registry describes how to build a node; it is not an inventory and never lists hosts. The hand-off to the orchestration controller is `confirmation.yml`.

The controller itself is three playbooks and a set of task files. Controller steps are task files in `tasks/`, because only these playbooks use them; transports stay roles, because each has its own settings, tests and safety rules and is chosen at run time by name.

## Requirements

- ansible-core 2.15 or later (developed with 2.21 and 2.22; earlier versions not yet tested)
- `git` on the controller host, for the check that keeps the secrets path out of the repository
- For the Incus transport: the `incus` client on the controller host, configured for the target Incus server

Everything runs on the controller host. No inventory or SSH access to the target is needed for the Incus transport. Run the playbooks from the repository root.

## Repository layout

```text
uc-raw-node/
├── ansible.cfg
├── build.yml                           Entry point: the full pipeline
├── validate.yml                        Registry and input checks only, nothing is built
├── destroy.yml                         Tear down a node by hostname
├── tasks/
│   ├── validate_registry.yml           Loads and checks every registry layer and entry
│   ├── load_registry_layer.yml         Loads one registry file
│   ├── load_input.yml                  Loads and checks the contract input
│   ├── resolve_platform.yml            Resolves target_platform and checks it can be used
│   ├── prepare_paths.yml               Expands and creates the output paths, checks the secrets path
│   ├── write_attempt.yml               Writes the attempt record before anything is created
│   ├── set_attempt_state.yml           Changes the attempt record's state
│   ├── payload.yml                     Renders raw-node-firstboot into the secrets path (placeholder)
│   ├── wait_phone_home.yml             Gets the node's address and host keys, writes the report
│   ├── write_confirmation.yml          Writes confirmation.yml
│   └── handle_failure.yml              Records the failure, then destroys or quarantines
├── vars/
│   └── defaults.yml                    Registry files, input fields, known transports, paths, timeouts
├── registry/
│   ├── base.yml                        Base platform registry
│   └── clients/
│       └── vishpala.yml                Client layer (empty)
├── roles/
│   ├── raw_node_transport_incus_exec/  Transport for Incus instances without cloud-init
│   └── raw_node_validator/             Checks the RN-* clauses on the built node (placeholder)
├── tests/
│   ├── prepare_paths.yml               Output path and secrets path checks
│   ├── transport_incus_exec.yml        The Incus transport, including the ownership marker
│   ├── build.yml                       build.yml with outputs under artifacts/ and test overrides
│   ├── build_scenarios.yml             Success, payload failure, teardown failure, placeholders
│   ├── destroy.yml                     destroy.yml with outputs under artifacts/
│   ├── destroy_scenarios.yml           Teardown with and without records, and refusals
│   ├── vars/output.yml                 Points every output path into artifacts/
│   ├── tasks/                          Per-case task files for the test playbooks
│   ├── fixtures/                       Test contract input and stand-in payloads
│   └── bin/incus                       Stand-in Incus client for hosts without Incus
├── records/                            Attempt, failure and confirmation records, ignored by git
├── reports/                            Address reports, ignored by git
├── logs/                               Transport and payload logs, ignored by git
└── artifacts/                          Development and test output only, ignored by git
```

`records/`, `reports/` and `logs/` are created on the first build. The secrets path is outside the repository and does not appear in the tree.

## Contract input

The contract input describes the node itself. Everything about the platform comes from the registry.

```yaml
hostname: web-01
root_password_hash: "$y$..."
initial_username: initial
initial_password_hash: "$y$..."
ssh_public_key: "ssh-ed25519 AAAA... you@workstation"
```

It is passed as extra vars, `-e @raw-node-input.yml`, from wherever you keep it; the secrets path is a suitable place. `-e raw_node_input_file=<path>` reads it from a file instead, which also warns about fields the controller does not use.

The controller checks every field before anything is created: the hostname must be a single lowercase DNS label, the user name must be valid and not `root`, both passwords must be crypt hashes (plaintext is rejected), and the key must be one OpenSSH public key line.

The hostname is the key of `confirmation.yml`, the instance name on platforms that name instances, and the name of the node's directories under the records, reports, logs and secrets paths.

## Usage

Check the registry, the input and the platform without building anything:

```sh
ansible-playbook validate.yml -e @raw-node-input.yml -e target_platform=incus_container_default
```

Build a node:

```sh
ansible-playbook build.yml -e @raw-node-input.yml -e target_platform=incus_container_default
```

Until `payload.yml` and `raw_node_validator` are written, `build.yml` stops inside its block with "not implemented yet", writes a failure record and cleans up.

Tear a node down by hostname. The platform is read from the node's attempt record; on a host without the record, add `-e target_platform=<key>`:

```sh
ansible-playbook destroy.yml -e hostname=web-01
```

The Incus transport only deletes an instance it created, which it recognises by its ownership marker (Incus user keys set at launch), and refuses to adopt an instance that already exists unless `-e raw_node_incus_allow_existing=true` is given. Choose the Incus project and image with `-e raw_node_incus_project=<project>` and `-e raw_node_incus_image=<image>` (default `images:debian/13`).

### Tests

Every test writes only under `artifacts/` (through `tests/vars/output.yml`) and is run from the repository root. With the stand-in Incus client first on the path, which checks the controller's logic and command sequence but not real Incus behaviour:

```sh
ansible-playbook -i localhost, -c local tests/prepare_paths.yml
PATH="$PWD/tests/bin:$PATH" ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_test_destroy=true
ansible-playbook -i localhost, -c local tests/build_scenarios.yml
ansible-playbook -i localhost, -c local tests/destroy_scenarios.yml
```

`tests/build_scenarios.yml` and `tests/destroy_scenarios.yml` put the stand-in client on the path themselves. On a host with Incus, use a dedicated project so nothing else can be touched:

```sh
incus project create uc-raw-node-test -c features.images=false -c features.profiles=false
ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_incus_project=uc-raw-node-test -e raw_node_test_destroy=true
ansible-playbook -i localhost, -c local tests/build_scenarios.yml -e raw_node_test_stand_in=false -e raw_node_incus_project=uc-raw-node-test
ansible-playbook -i localhost, -c local tests/destroy_scenarios.yml -e raw_node_test_stand_in=false -e raw_node_incus_project=uc-raw-node-test
```

## Output and secrets

| Path | Setting | Holds |
| :-- | :-- | :-- |
| `records/<hostname>/` | `raw_node_records_path` | `attempt.yml`, `failure.yml`, `confirmation.yml` |
| `reports/<hostname>/` | `raw_node_reports_path` | `report.yml`: addresses and SSH host public keys |
| `logs/<hostname>/` | `raw_node_logs_path` | Transport and payload logs |
| `~/.secrets/uc-raw-node/<hostname>/` | `raw_node_secrets_path` | Rendered payload and phone-home token, deleted after use |

Each setting can be overridden with `-e`. Records and reports hold public data only. Logs hold the transport's and the payload's output, which the payload's output rules keep free of contract values.

### Operational notes

- **Records are operational state.** `destroy.yml` reads a node's platform from `records/<hostname>/attempt.yml`, and the orchestration controller reads `confirmation.yml`. Deleting a node's records breaks `destroy.yml` for that node until `-e target_platform` is supplied, and removes the hand-off for a confirmed node. `records/` is ignored by git, so records exist only on the controller host that built the node.
- **The secrets path** is `~/.secrets/uc-raw-node` by default, outside the repository. The controller creates its missing directories with mode 0700, writes files with mode 0600, and stops if the secrets path or a node's directory already exists with looser permissions, or if the path is inside the repository and not ignored by git. Existing parents such as `~/.secrets` are left as they are.
- **Backups and cloud sync.** The secrets path and, with a home directory checkout, `records/` sit under the controller host's home directory by default, so any backup or cloud sync of that directory copies them to other devices. The controller cannot prevent that. The payload and token are deleted after use, which limits what a backup can catch, but does not make the secrets path safe to sync.
- **A second controller host** starts with an empty secrets path, which is harmless because tokens are single-use, and with no records either. On that host, `destroy.yml` needs `-e target_platform`, and the transport's ownership marker, which lives on the platform, still decides what may be deleted. A shared records location is deferred until several hosts must manage the same nodes.

## The platform registry

The base registry is `registry/base.yml`. A client or site adds its own layer under `registry/clients/` and appends it to `raw_node_registry_files`, for example:

```sh
ansible-playbook validate.yml -e @raw-node-input.yml -e target_platform=incus_container_default \
  -e '{"raw_node_registry_files": ["registry/base.yml", "registry/clients/vishpala.yml"]}'
```

Later files are merged over earlier ones, lists are replaced, and an entry is retired by setting its `status` to `excluded` rather than deleting it.

Every entry starts as `unverified`. A maintainer changes it to `active` after a node built on the real platform has passed the validator; the controller never writes to the registry. Fallback between entries is limited to one hop, so loops cannot occur.

To add a platform:

- **On an existing transport:** add an entry to the registry or to a client layer. Validation will tell you if a field is missing or invalid.
- **On a new transport:** also write a `raw_node_transport_<name>` role and add its name to `raw_node_known_transports`. Until then, selecting the platform stops with a message naming the missing role. A transport that can destroy instances records an ownership marker on each instance it creates (Incus user keys, or tags on a cloud provider) and checks it before every delete; see `roles/raw_node_transport_incus_exec/README.md`.

## Build order

Two kinds of raw node come first, in this order:

- **Priority 1: a Debian 13 container on a local Incus server.** The registry entry `incus_container_default` (`adopt` strategy, `incus_exec` transport) with the image `images:debian/13`. The controller can already build, report, confirm and destroy such a container safely; what remains is the payload and the validator:
  - Write `payload.yml` and `templates/raw-node-firstboot.j2`, which need the `RN-*` clauses pinned down.
  - Write `raw_node_validator`.
  - Build a node with `build.yml` on a real Incus host, and mark `incus_container_default` `active` once it passes the validator.
- **Priority 2: a Debian 13 VPS.** Needs a new transport role, and probably a strategy other than `adopt`, plus the phone-home receiver if the provider does not report addresses. It replaces `incus_container_cloud` as the next platform after priority 1. The transport follows the ownership marker rule with whatever the provider offers, such as instance tags.

Then, in order:

- `raw_node_transport_ssh`, for SSH-only VPS hosts.
- `incus_container_cloud`, which falls back to `incus_container_default` and exercises the `cloud_init` strategy, single-hop fallback and the firewall probe on the local Incus host.

## Design documents

The design is recorded in three versioned documents, which are the authority when this README and the code disagree:

- *Collapse Strategy for a Raw Node Controller* (`en/docs/collapsable-strategy-for-a-raw-node-controller-v0.1.11.md`): scope, strategies, transports, per-platform issue analysis, failure handling, credential exposure and the phone-home design.
- *The Platform Registry* (`en/docs/1-the-platform-registry-v0.1.5.md`): registry fields, contents, layering, validation and the consumer logic.
- *Raw Node Controller Layout Design* (`en/docs/design/raw-node-controller-layout-design-v0.1.8.md`): how the controller is laid out on disk, which parts are task files and which are roles, the output directories and secrets path, the step contracts, variable naming, and the migration from the old layout.

Working sessions are recorded in `en/docs/sessions/`.

## Related

- **uc-ventoy:** generates the Ventoy USB installs for bare metal and VMs. uc-raw-node treats it as the `ventoy_usb` transport for the `installer` strategy rather than reimplementing it. It shares the contract input format, so it needs the same `hostname` field.
