# The Platform Registry

- **Version:** 0.1.4
- **Date:** 2026-11-20
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose

The platform registry is the data that tells `uc-raw-node` how to build a raw node on a given platform: which delivery strategy to use, which transport delivers the payload, and what the platform can and cannot do. It is the single authority for registry fields, contents and consumer logic. The design that the registry serves is described in [Collapse Strategy for a Raw Node Controller](collapsable-strategy-for-a-raw-node-controller-v0.1.10.md).

Only the raw node controller reads the registry. The orchestration controller never does.

## Registry versus inventory

An Ansible inventory describes hosts that exist, so Ansible can reach them over SSH, `incus exec` or another connection. The registry describes how to build a new host on a platform. It is not tied to any running instance.

The two meet at `confirmation.yml`. The controller reads the registry to build a node, writes `confirmation.yml` once the node meets the contract, and the orchestration controller turns that confirmation into inventory. The registry never lists hosts, and the inventory never says how a host was built.

The registry is configuration, not state. The controller never writes to it; every change, including a change of `status`, is made by a maintainer.

## Location and layering

The registry is not stored in the role's `vars/` directory. Role vars override play vars and inventory variables, so a client could not easily change or extend a registry kept there; values in a role's `defaults/` are the ones meant to be overridden <a id="cite-ansible-precedence"></a>[(Ansible Project, n.d.)](#ref-ansible-precedence).

Instead, the registry is plain YAML in one or more files, listed in `raw_node_registry_files`:

- The base registry ships with the role at `roles/raw_node_controller/files/registry.yml`.
- A client or site can add its own file after the base one, to add platforms or change entries. Later files are merged over earlier ones.

This follows the same pattern as a configuration cascade: shared defaults first, then the more specific layers.

### Merge rules

- Each layer must be a mapping with exactly one top-level key, `platforms`, whose value is a mapping of entries.
- Entries are merged field by field: a later layer can add an entry or change individual fields of an existing one.
- Lists, such as `vps_modes`, are replaced, not appended to.
- A layer cannot delete an entry. To stop an entry being used, a later layer sets its `status` to `excluded` and says why in `notes`.

### Defaults

```yaml
# roles/raw_node_controller/defaults/main.yml
raw_node_registry_files:
  - "{{ role_path }}/files/registry.yml"

raw_node_input_file: "{{ playbook_dir }}/raw-node-input.yml"

raw_node_input_required_fields:
  - hostname
  - root_password_hash
  - initial_username
  - initial_password_hash
  - ssh_public_key

raw_node_artifacts_dir: "{{ playbook_dir }}/artifacts/{{ raw_node_hostname }}"

raw_node_strategies:
  - cloud_init
  - installer
  - image
  - adopt

# Only list transports whose raw_node_transport_<name> role exists.
# incus_exec is the first transport with a role.
raw_node_known_transports:
  - incus_exec

raw_node_platform_defaults:
  datasource: null
  fallback: null
  phone_home: required
  firewall_clause: applies
  vps_modes: []
  status: unverified
  notes: ""
```

## Field reference

| Field | Type | Required | Allowed values | Default | Meaning |
| :-- | :-- | :-- | :-- | :-- | :-- |
| `strategy` | string | Yes | A name in `raw_node_strategies` | None | How the payload is packaged and run |
| `transport` | string | Yes | Any name; must be in `raw_node_known_transports` to be used | None | Which `raw_node_transport_<name>` role delivers the payload |
| `datasource` | string | For `cloud_init` | A cloud-init datasource name | `null` | The datasource cloud-init should use on this platform |
| `can_destroy` | boolean | Yes | `true`, `false` | None | Whether a failed node can be deleted automatically |
| `reports_address` | boolean | Yes | `true`, `false` | None | Whether the platform or transport gives the controller the node's address without phone-home |
| `phone_home` | string | No | `required`, `optional`, `local` | `required` | Whether phone-home is required, a second source of evidence, or written to local media |
| `firewall_clause` | string | No | `applies`, `check`, `waived` | `applies` | Whether the baseline nftables clause applies, must be probed first, or has a defined waiver |
| `fallback` | string | No | Another key in `platforms` | `null` | The entry to use if this one cannot work; one hop only, see registry validation |
| `vps_modes` | list | For VPS entries | `user_data`, `ssh_only`, `rescue`, `custom_iso` | `[]` | Metadata only: which VPS modes the provider supports |
| `status` | string | No | `active`, `unverified`, `excluded` | `unverified` | Whether the entry has been tested on the real platform, or is deliberately not supported |
| `notes` | string | No | Free text | `""` | Anything a maintainer needs to know |

An entry becomes `active` only when a maintainer changes its status, after a node has been built on the real platform and has passed `raw_node_validator`. Until then the raw node controller (uc-raw-node) uses the entry but warns. An `excluded` entry is kept so the reason is recorded, and the raw node controller refuses to use it. The orchestration controller never reads the registry.

### vps_modes is metadata

`vps_modes` does not affect routing. The controller never chooses a mode on its own; the operator chooses one by choosing the registry entry. When a provider supports several modes the controller should use, each mode gets its own entry (for example, `hetzner_cloud` for user-data and `rescue_dd` for rescue mode), and `vps_modes` records what the provider offers so a maintainer knows which entries could be added. If mode-based routing is ever needed, it can be added as a small router in front of the registry without changing the entries.

## Base registry

```yaml
# roles/raw_node_controller/files/registry.yml
# Platform-to-strategy mapping for the uc-raw-node controller.

platforms:

  # Cloud and VPS with API and user-data

  hetzner_cloud:
    strategy: cloud_init
    transport: hetzner_api
    datasource: hetzner
    can_destroy: true
    reports_address: true
    vps_modes: [user_data, rescue, custom_iso]

  digitalocean_cloud:
    strategy: cloud_init
    transport: do_api
    datasource: digitalocean
    can_destroy: true
    reports_address: true
    vps_modes: [user_data, custom_iso]

  # Local hypervisors

  incus_vm_cloud:
    strategy: cloud_init
    transport: incus
    datasource: nocloud
    can_destroy: true
    reports_address: true

  proxmox_vm:
    strategy: cloud_init
    transport: proxmox_api
    datasource: nocloud
    can_destroy: true
    reports_address: true

  # Containers on Incus or LXD

  incus_container_cloud:
    strategy: cloud_init
    transport: incus
    datasource: nocloud
    can_destroy: true
    reports_address: true
    phone_home: optional
    firewall_clause: check
    fallback: incus_container_default
    notes: "For /cloud image variants, which include cloud-init."

  incus_container_default:
    strategy: adopt
    transport: incus_exec
    can_destroy: true
    reports_address: true
    phone_home: optional
    firewall_clause: check
    notes: "Default image variants lack cloud-init; raw-node-firstboot is pushed and run with incus file push and incus exec. First priority for implementation."

  # VPS without user-data

  vps_ssh_only:
    strategy: adopt
    transport: ssh
    can_destroy: false
    reports_address: false
    firewall_clause: check
    vps_modes: [ssh_only]
    notes: "Reinstall the provider template from the panel before adopting. Teardown is manual. firewall_clause is check because some SSH-only products are container-based."

  # EX2

  ex2_vps_standard:
    strategy: adopt
    transport: ssh
    can_destroy: false
    reports_address: false
    status: excluded
    notes: "Default cPanel/CloudLinux images are panel-managed and not raw nodes. Reinstall a plain OS template and use ex2_vps_plain."

  ex2_vps_plain:
    strategy: adopt
    transport: ssh
    can_destroy: false
    reports_address: false
    firewall_clause: check
    vps_modes: [ssh_only]
    notes: "Assumes EX2 offers a plain OS template. To confirm."

  ex2_vps_custom:
    strategy: cloud_init
    transport: ex2_api
    datasource: nocloud
    can_destroy: true
    reports_address: true
    fallback: ex2_vps_plain
    vps_modes: [user_data]
    notes: "Assumes a cloud-enabled custom image and an EX2 API that injects user-data and can destroy instances. Datasource and capabilities to confirm."

  # Bare metal and hosted rescue

  metal_ventoy:
    strategy: installer
    transport: ventoy_usb
    can_destroy: false
    reports_address: false
    notes: "Controller has no visibility of boot. Phone-home is mandatory."

  rescue_dd:
    strategy: image
    transport: rescue_ssh
    can_destroy: false
    reports_address: true
    notes: "Hosted dedicated server or VPS booted into the provider's rescue system. Image deployed with dd, rsync or installimage. The address is known because the controller connects to the rescue system."

  # Air-gapped

  airgap_local_media:
    strategy: image
    transport: local_media
    can_destroy: false
    reports_address: false
    phone_home: local
    notes: "Image deployed from local media with dd, rsync or DRBL. The phone-home report is written to local media for later collection."
```

Every entry is `unverified` by default, because none has yet been built and validated on its real platform.

## Registry validation

Before anything is built, the controller loads and checks the whole registry, not only the entry it is about to use. A mistake in an entry that is not used today should still be caught today, not when someone first selects it.

The checks happen in three stages:

- **Each layer on its own.** Every file must parse as YAML and have the shape described in the merge rules. A file that fails is reported by its path, so a malformed client layer is easy to find.
- **Every entry in the merged registry.** Required fields are present, values are in their allowed sets, and `cloud_init` entries have a `datasource`.
- **Every fallback.** A fallback must point to another existing entry, must not point to itself, must not point to an excluded entry, and its target must not have a fallback of its own.

The last rule limits fallback to a single hop. That makes loops impossible by construction, so no separate cycle detection is needed, and it matches the design rule that a fallback after failure is attempted once. A chain such as `incus_container_cloud` to `incus_container_default` is allowed; a chain of three is not.

Whether a transport is implemented is checked only for the entry being used, not for the whole registry. The registry legitimately lists platforms whose transport roles have not been written yet.

### Loading one layer

```yaml
# roles/raw_node_controller/tasks/load_registry_layer.yml
- name: "Load registry layer {{ raw_node_registry_file }}"
  block:
    - name: Parse layer
      ansible.builtin.set_fact:
        raw_node_registry_layer: "{{ lookup('ansible.builtin.file', raw_node_registry_file) | from_yaml }}"

    - name: Check layer shape
      ansible.builtin.assert:
        that:
          - raw_node_registry_layer is mapping
          - raw_node_registry_layer.keys() | list == ['platforms']
          - raw_node_registry_layer.platforms is mapping
        quiet: true

    - name: Merge layer
      ansible.builtin.set_fact:
        raw_node_registry: >-
          {{ raw_node_registry | default({})
             | combine(raw_node_registry_layer, recursive=True) }}

  rescue:
    - name: Report unusable layer
      ansible.builtin.fail:
        msg: >-
          Registry layer {{ raw_node_registry_file }} could not be loaded
          or does not have the expected shape (a mapping with a single
          'platforms' key). {{ ansible_failed_result.msg | default('') }}
```

### Validating the merged registry

```yaml
# roles/raw_node_controller/tasks/validate_registry.yml
- name: Load registry layers in order
  ansible.builtin.include_tasks: load_registry_layer.yml
  loop: "{{ raw_node_registry_files }}"
  loop_control:
    loop_var: raw_node_registry_file

- name: Check every registry entry
  ansible.builtin.assert:
    that:
      - entry is mapping
      - entry.strategy is defined and entry.strategy in raw_node_strategies
      - entry.transport is defined and entry.transport is string
      - entry.can_destroy is defined and entry.can_destroy is boolean
      - entry.reports_address is defined and entry.reports_address is boolean
      - entry.strategy != 'cloud_init' or (entry.datasource | default(none)) is not none
      - (entry.phone_home | default('required')) in ['required', 'optional', 'local']
      - (entry.firewall_clause | default('applies')) in ['applies', 'check', 'waived']
      - (entry.status | default('unverified')) in ['active', 'unverified', 'excluded']
    fail_msg: "Registry entry '{{ item.key }}' is missing a required field or has a value outside its allowed set."
    quiet: true
  loop: "{{ raw_node_registry.platforms | dict2items }}"
  loop_control:
    label: "{{ item.key }}"
  vars:
    entry: "{{ item.value }}"

- name: Check every fallback is a single safe hop
  ansible.builtin.assert:
    that:
      - item.value.fallback in raw_node_registry.platforms
      - item.value.fallback != item.key
      - (raw_node_registry.platforms[item.value.fallback].status | default('unverified')) != 'excluded'
      - (raw_node_registry.platforms[item.value.fallback].fallback | default(none)) is none
    fail_msg: >-
      Fallback for '{{ item.key }}' must point to another existing,
      non-excluded entry that has no fallback of its own.
    quiet: true
  loop: >-
    {{ raw_node_registry.platforms | dict2items
       | selectattr('value.fallback', 'defined')
       | rejectattr('value.fallback', 'none')
       | list }}
  loop_control:
    label: "{{ item.key }}"
```

The conditions in each assert are checked in order and stop at the first one that fails, so the later fallback conditions are never evaluated for a fallback that does not exist.

## Consumer logic

The entry point validates the registry, loads and checks the contract input, then resolves the requested platform and applies defaults before dispatching. It does not use `hosts` or `groups`. Platform resolution is kept in its own file, `resolve_platform.yml`, so tests and tools can validate and resolve a platform without building anything. The contract input checks in `load_input.yml` are described in the design document.

```yaml
# roles/raw_node_controller/tasks/main.yml
- name: Load and validate the registry
  ansible.builtin.include_tasks: validate_registry.yml

- name: Load and check the contract input
  ansible.builtin.include_tasks: load_input.yml

- name: Resolve and check the target platform
  ansible.builtin.include_tasks: resolve_platform.yml

- name: Build, deliver and validate
  block:
    - name: Render raw-node-firstboot payload
      ansible.builtin.include_tasks: payload.yml

    - name: Render strategy artifacts
      ansible.builtin.include_tasks: "{{ raw_node_delivery_strategy }}/artifacts.yml"

    - name: Deliver through transport
      ansible.builtin.include_role:
        name: "raw_node_transport_{{ raw_node_platform.transport }}"

    - name: Wait for phone-home report
      ansible.builtin.include_tasks: wait_for_phone_home.yml

    - name: Validate contract
      ansible.builtin.include_role:
        name: raw_node_validator

    - name: Write confirmation.yml
      ansible.builtin.include_tasks: write_confirmation.yml

  rescue:
    - name: Handle failure by platform capability
      ansible.builtin.include_tasks: failure.yml
```

```yaml
# roles/raw_node_controller/tasks/resolve_platform.yml
- name: Assert platform is in the registry
  ansible.builtin.assert:
    that:
      - target_platform is defined
      - target_platform in raw_node_registry.platforms
    fail_msg: "Platform '{{ target_platform | default('undefined') }}' is not in the registry."

- name: Resolve platform entry with defaults
  ansible.builtin.set_fact:
    raw_node_platform: >-
      {{ raw_node_platform_defaults
         | combine(raw_node_registry.platforms[target_platform]) }}

- name: Assert platform is not excluded
  ansible.builtin.assert:
    that:
      - raw_node_platform.status != 'excluded'
    fail_msg: "Platform '{{ target_platform }}' is excluded: {{ raw_node_platform.notes }}"

- name: Assert transport role exists
  ansible.builtin.assert:
    that:
      - raw_node_platform.transport in raw_node_known_transports
    fail_msg: >-
      Transport '{{ raw_node_platform.transport }}' for platform
      '{{ target_platform }}' has no raw_node_transport_{{ raw_node_platform.transport }}
      role yet. Write the role and add the name to raw_node_known_transports.

- name: Resolve delivery strategy
  ansible.builtin.set_fact:
    raw_node_delivery_strategy: "{{ raw_node_strategy_override | default(raw_node_platform.strategy) }}"

- name: Assert strategy override is valid
  ansible.builtin.assert:
    that:
      - raw_node_delivery_strategy in raw_node_strategies
    fail_msg: "Strategy '{{ raw_node_delivery_strategy }}' is not one of {{ raw_node_strategies | join(', ') }}."

- name: Warn about unverified platform entry
  ansible.builtin.debug:
    msg: "Platform '{{ target_platform }}' has not been validated on its real platform yet."
  when: raw_node_platform.status == 'unverified'
```

The transport role reads `raw_node_platform` and `raw_node_artifacts_dir` directly, so `include_role` passes no extra variables. `failure.yml` uses `can_destroy` and `fallback` to decide between destroying, a single fallback attempt, and quarantine, as set out in the design document's failure and fallback sections.

## Adding a platform

There are two cases:

- **The transport already exists.** Adding the platform is data only: a new entry in the base registry or in a client layer. It starts as `unverified` and becomes `active` once a maintainer has built a node on it that passed validation.
- **The transport is new.** Adding the platform also needs one `raw_node_transport_<name>` role and the transport's name in `raw_node_known_transports`. Until both exist, the entry passes registry validation but selecting it stops at the "Assert transport role exists" check with a message naming the missing role. Adding AWS Lightsail, for example, needs a Lightsail or AWS API transport role before its entry can be used.

`raw_node_known_transports` is maintained by hand, next to the transport roles. Keeping it short and explicit is deliberate: it keeps the scope of what the controller claims to support tight.

## Build order

`incus_container_default` is the first entry to implement, followed by `incus_container_cloud`, which falls back to it. Together they exercise the `adopt` and `cloud_init` strategies, the `incus` and `incus_exec` transports, single-hop fallback, and the `firewall_clause: check` probe, all on the local Incus host before any provider account is involved.

The work for the first entry, in order, with its status:

- **`validate_registry.yml` and `load_registry_layer.yml`.** Done. They are small, have no dependencies, and protect everything after them.
- **`payload.yml`.** Not started. It renders `raw-node-firstboot` from `raw-node-input.yml`. It needs the `RN-*` clauses pinned down, because the payload is where they are implemented.
- **`raw_node_transport_incus_exec`.** Scaffolded and tested with a stand-in Incus client; a run on a real Incus host is still needed. It pushes and runs the payload with `incus file push` and `incus exec`, and `incus_exec` is now in `raw_node_known_transports`.
- **`raw_node_validator`.** Not started. It is needed before any entry can become `active`.

`raw_node_transport_ssh` comes after that. It is needed for `vps_ssh_only` and the EX2 entries, not for the Incus entries, and can reuse most of the payload handling from `incus_exec`.

## Open questions

- Does EX2 offer plain OS templates alongside the cPanel/CloudLinux images?
- Does the EX2 API accept user-data, and if so, which cloud-init datasource does a custom image see, and can the API destroy instances?
- Should client layers be allowed to override fields of a base entry, or only add new entries and exclude existing ones?

## Changes

### From v0.1.3 to v0.1.4

- Brought the defaults and consumer logic in line with the scaffolded code: platform resolution moved to `resolve_platform.yml`, `main.yml` now loads the contract input with `load_input.yml`, and `incus_exec` is listed in `raw_node_known_transports`.
- Added `raw_node_input_file` and `raw_node_input_required_fields` (including the new `hostname` field) to the defaults, and keyed `raw_node_artifacts_dir` by hostname instead of platform, so two nodes on the same platform do not share artifacts.
- Added the status of each item in the build order.

### From v0.1.2 to v0.1.3

- Stated that only the raw node controller reads the registry, that the registry is configuration and never written by the controller, and that a maintainer changes `status`.
- Added merge rules for layers: required shape, field-by-field merge, lists replaced, entries excluded rather than deleted.
- Added registry validation (`validate_registry.yml` and `load_registry_layer.yml`): per-layer parsing with a block and rescue that names the failing file, checks on every entry, and fallback limited to one hop so that loops cannot occur.
- Split the per-platform asserts so that excluded entries, missing transport roles and invalid strategy overrides each give their own message.
- Added `raw_node_strategies` to the defaults, and set `raw_node_known_transports` to empty until the first transport role exists.
- Documented `vps_modes` as metadata that does not affect routing, with one entry per mode the controller should use.
- Expanded the build order into the concrete work for the first entry, and placed `raw_node_transport_ssh` after it.

## References

<a id="ref-ansible-precedence"></a>Ansible Project. (n.d.). *Using variables: Variable precedence*. Ansible documentation. https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html
[Return to citation](#cite-ansible-precedence)
