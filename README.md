# uc-raw-node

uc-raw-node is the raw node controller. It takes a short contract input file and a target platform, builds a node on that platform that meets the raw node contract (the `RN-*` clauses), and writes `confirmation.yml` so the orchestration controller can take over.

It does one job only. Discovery, onboarding, normalization and customization belong to the orchestration controller, and infrastructure-as-code tools such as Terraform, OpenTofu or Pulumi call uc-raw-node from outside rather than living inside it.

- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Status

The layout is about to change from the controller role to playbooks with task files. See latest version of [raw-node-controller-layout-design-v0.1.8.md](en/docs/design/raw-node-controller-layout-design-v0.1.8.md) for details and in the mean time do not to build on `roles/raw_node_controller/`

Early scaffold. The registry, its validation, contract input checking and the first transport are written and tested; the payload and the validator are not started, so the controller cannot build a complete raw node yet.

| Part | Status |
| :-- | :-- |
| Platform registry and `validate_registry.yml` | Done, tested |
| Contract input checking (`load_input.yml`) | Done, tested |
| `raw_node_transport_incus_exec` | Scaffolded, tested with a stand-in Incus client; needs a run on a real Incus host |
| `payload.yml` (renders `raw-node-firstboot`) | Not started |
| `raw_node_validator` | Not started |
| Phone-home receiver, failure handling | Not started |
| Other transports (`ssh`, `incus`, provider APIs, `ventoy_usb`) | Not started |

## How it works

The controller collapses many platforms into a small number of moving parts:

- **One payload.** Every node is set up by the same script, `raw-node-firstboot`, which creates the initial user, installs the SSH key, sets the root password hash, applies the baseline nftables ruleset and reports back. The `RN-*` clauses are implemented once, there.
- **Four strategies.** A strategy decides how the payload is packaged: `cloud_init` (cloud-config user-data), `installer` (Preseed, Kickstart or Subiquity autoinstall), `image` (baked into a disk image) or `adopt` (pushed over a channel that already exists, such as SSH or `incus exec`).
- **Transports.** A transport is a small role that delivers the packaged payload to the platform, for example `raw_node_transport_incus_exec`. This is the pluggable part.
- **A platform registry.** Plain YAML that says, for each platform, which strategy and transport to use and what the platform can do (whether a failed node can be destroyed, whether it reports its address, whether the firewall clause applies). Adding a platform on an existing transport is a data change only.
- **One validator.** The contract is checked the same way no matter how the node was built.

The registry describes how to build a node; it is not an inventory and never lists hosts. The hand-off to the orchestration controller is `confirmation.yml`.

## Requirements

- ansible-core 2.15 or later (developed and tested with 2.22; earlier versions not yet tested)
- For the Incus transport: the `incus` client on the controller host, configured for the target Incus server

Everything runs on the controller host. No inventory or SSH access to the target is needed for the Incus transport.

## Repository layout

```text
uc-raw-node/
├── ansible.cfg
├── roles/
│   ├── raw_node_controller/
│   │   ├── defaults/main.yml           Registry files, input fields, known transports
│   │   ├── files/registry.yml          Base platform registry
│   │   └── tasks/
│   │       ├── main.yml                Entry point
│   │       ├── validate_registry.yml   Loads and checks every registry layer and entry
│   │       ├── load_registry_layer.yml Loads one registry file
│   │       ├── load_input.yml          Loads and checks raw-node-input.yml
│   │       └── resolve_platform.yml    Resolves target_platform and checks it can be used
│   └── raw_node_transport_incus_exec/  Transport for Incus instances without cloud-init
└── tests/
    ├── transport_incus_exec.yml        End-to-end test of the Incus transport
    ├── fixtures/                       Test contract input and stand-in payload
    └── bin/incus                       Stand-in Incus client for hosts without Incus
```

## Contract input

`raw-node-input.yml` describes the node itself. Everything about the platform comes from the registry.

```yaml
hostname: web-01
root_password_hash: "$y$..."
initial_username: initial
initial_password_hash: "$y$..."
ssh_public_key: "ssh-ed25519 AAAA... you@workstation"
```

The controller checks every field before anything is created: the hostname must be a single lowercase DNS label, the user name must be valid and not `root`, both passwords must be crypt hashes (plaintext is rejected), and the key must be one OpenSSH public key line. Unknown fields produce a warning, not an error.

The hostname is the key of `confirmation.yml`, the instance name on platforms that name instances, and the name of the node's artifacts directory.

## Usage

The full build path (`roles/raw_node_controller/tasks/main.yml`) needs `payload.yml` and the validator, which do not exist yet. Today the registry, input checks and Incus transport can be exercised through the test playbook.

On a host with Incus:

```sh
ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_test_destroy=true
```

On a host without Incus, put the stand-in client first on the path. It checks the role's logic and command sequence, not real Incus behaviour:

```sh
PATH="$PWD/tests/bin:$PATH" ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_test_destroy=true
```

The test builds `incus_container_default` with the input in `tests/fixtures/raw-node-input.yml` and a stand-in payload. Without `raw_node_test_destroy=true` the test instance is kept; delete it with `incus delete --force rn-test-incus-exec`. The transport refuses to touch an instance that already exists unless `raw_node_incus_allow_existing=true` is set, and never deletes an instance it did not create.

Output, including the payload's exit code and log, goes to `artifacts/<hostname>/`, which is ignored by git.

## The platform registry

The base registry is `roles/raw_node_controller/files/registry.yml`. A client or site adds its own layer by appending a file to `raw_node_registry_files`; later files are merged over earlier ones, lists are replaced, and an entry is retired by setting its `status` to `excluded` rather than deleting it.

Every entry starts as `unverified`. A maintainer changes it to `active` after a node built on the real platform has passed the validator; the controller never writes to the registry. Fallback between entries is limited to one hop, so loops cannot occur.

To add a platform:

- **On an existing transport:** add an entry to the registry or to a client layer. Validation will tell you if a field is missing or invalid.
- **On a new transport:** also write a `raw_node_transport_<name>` role and add its name to `raw_node_known_transports`. Until then, selecting the platform stops with a message naming the missing role.

## Build order

The first registry entry being built is `incus_container_default`, followed by `incus_container_cloud`, which falls back to it. Both run on a local Incus host, so the strategies, transports, fallback and firewall probe can be tested before any provider account is involved.

Next steps, in order:

- Run the Incus transport test on a real Incus host.
- Write `payload.yml`, which needs the `RN-*` clauses pinned down.
- Write `raw_node_validator`.
- Then `raw_node_transport_ssh`, for SSH-only VPS hosts.

## Design documents

The design is recorded in two versioned documents, which are the authority when this README and the code disagree:

- *Collapse Strategy for a Raw Node Controller* (`collapsable-strategy-for-a-raw-node-controller-v0.1.10.md`): scope, strategies, transports, per-platform issue analysis, failure handling, credential exposure and the phone-home design.
- *The Platform Registry* (`1-the-platform-registry-v0.1.4.md`): registry fields, contents, layering, validation and the consumer logic.

## Related

- **uc-ventoy:** generates the Ventoy USB installs for bare metal and VMs. uc-raw-node treats it as the `ventoy_usb` transport for the `installer` strategy rather than reimplementing it. It shares the contract input format, so it needs the same `hostname` field.
