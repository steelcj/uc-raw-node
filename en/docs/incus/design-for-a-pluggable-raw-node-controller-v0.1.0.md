# Design for a Pluggable Raw Node Controller

## Executive Summary

The raw node controller must act as a unified orchestration layer that abstracts away the delivery mechanism. Whether a node is provisioned via cloud-init (Incus, cloud providers), an installer answer file (Preseed, Subiquity), or a custom image, the controller's responsibility is to ensure the node meets the raw node contract (the baseline) and produces the `confirmation.yml` report.

By adopting a **Provider Pattern**, the controller delegates the "how" of creation to pluggable providers while retaining strict control over the "what" (the contract). This design ensures that adding a new creation method—such as a kickstart-based bare-metal provisioner or a specialized live-ISO builder—requires no changes to the core controller logic, only the addition of a new provider role.

## Core Principles

1. **Contract-First:** The controller validates the contract before and after creation. The delivery mechanism is irrelevant to the validation phase.
2. **Separation of Concerns:** Artifact generation (creating configuration files) is decoupled from execution (launching the node).
3. **Pluggable Providers:** Delivery methods are encapsulated in isolated roles. The controller dispatches to a provider based on a configuration variable.
4. **Standardized Interface:** All providers consume the same `raw-node-input.yml` and guarantee the same outputs (e.g., `/var/lib/raw-node/confirmation.yml`, canonical files).

## Architectural Design

The controller follows a three-phase architecture: **Prepare**, **Provision**, and **Verify**.

### Phase 1: Prepare (Artifact Generation)

The first phase translates `raw-node-input.yml` into platform-specific configuration artifacts. This phase is largely platform-agnostic because the input is universal; the difference lies in the output format.

| Provider   | Input                | Generated Artifact                 |
| ---------- | -------------------- | ---------------------------------- |
| Cloud-init | `raw-node-input.yml` | `user-data.yaml`, `meta-data.yaml` |
| Preseed    | `raw-node-input.yml` | `preseed.cfg`, `auto-installer.sh` |
| Subiquity  | `raw-node-input.yml` | `autoinstall.yaml`                 |

**Implementation:** Use Jinja2 templates within the controller's role to generate these files dynamically.

### Phase 2: Provision (Execution)

The second phase is where the delivery mechanism diverges. The controller instructs the selected provider to use the generated artifacts to create the node.

* **Cloud-init Provider:** Uses the `community.general.incus_container` module (or cloud provider SDKs) to launch an instance with the `user-data` injected.
* **Installer Provider:** Uses tools like `kiwi-ng`, `virt-install`, or `mkisofs` to build an ISO containing the preseed/subiquity files, then boots the target.
* **Image Provider:** Calls a build system (e.g., Packer) to bake the configuration into a static image, then deploys that image.

### Phase 3: Verify (Contract Enforcement)

The final phase connects to the newly created node and runs the contract checks. This is the phase that proved robust during the Incus spike.

* **Checks:** Validates `confirmation.yml` existence, firewall state, SSH configuration, and canonical file checksums.
* **Outcome:** If verification fails, the controller tears down the node and reports the failure.

## Ansible Implementation Strategy

The controller is implemented as a collection of Ansible roles. This structure leverages Ansible's modular nature and allows for easy testing of individual components.

### Directory Structure

```text
roles/
└── raw_node_controller/
 ├── tasks/
 │ ├── 01_prepare.yml # Generates artifacts based on input
 │ ├── 02_provision.yml # Dispatches to the selected provider
 │ └── 03_verify.yml # Runs the contract validator
 └── templates/
 ├── user-data.j2
 ├── preseed.j2
 └── autoinstall.j2

roles/
└── raw_node_provider_cloud_init/
 ├── tasks/
 │ └── main.yml # Uses community.general.incus_container
 └── defaults/
 └── main.yml

roles/
└── raw_node_provider_installer/
 ├── tasks/
 │ └── main.yml # Uses community.general.virt_install or kiwi-ng
 └── defaults/
 └── main.yml

roles/
└── raw_node_validator/
 ├── tasks/
 │ └── main.yml # SSHs to the node, runs spike checks
 └── handlers/
 └── main.yml
```

### Dispatch Logic

The core controller uses a simple variable to select the provider. This keeps the main playbook clean and decoupled.

```yaml
# roles/raw_node_controller/tasks/02_provision.yml
- name: Provision node using selected provider
 import_role:
 name: "raw_node_provider_{{ raw_node_delivery_method }}"
 vars:
 raw_node_artifact_path: "{{ artifact_dir }}"
```

### Variable Management

All providers share a common set of defaults but can override them. For example, the cloud-init provider might default to using an `incus` backend, while the installer provider defaults to `local_iso`.

```yaml
# defaults/main.yml (shared)
raw_node_delivery_method: cloud_init
raw_node_contract_version: "0.3.0"

# defaults/main.yml (cloud-init specific)
raw_node_incus_project: default
raw_node_incus_profile: default
```

## Extensibility: Adding a New Provider

Adding a new creation method, such as a `kickstart` provider for bare-metal servers, requires three steps:

1. **Create a Role:** Create `roles/raw_node_provider_kickstart/` with its own `tasks/main.yml`.
2. **Implement Execution:** The role's tasks generate the `ks.cfg` artifact and call `anaconda` or `kickstart` via `virt-install` or a PXE server.
3. **Register:** No changes are needed to the controller. As long as the role is present and the user sets `raw_node_delivery_method: kickstart`, the controller dispatches automatically.

## References

Canonical. (n.d.). *Cloud-init documentation*. https://cloud-init.io/

Gamma, E., Helm, R., Johnson, R., & Vlissides, J. (1994). *Design patterns: Elements of reusable object-oriented software*. Addison-Wesley.

Linux Containers. (n.d.). *Incus documentation*. https://linuxcontainers.org/incus/docs/latest/

Red Hat. (n.d.). *Ansible User Guide*. https://docs.ansible.com/ansible/latest/user_guide/index.html
```