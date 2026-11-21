# Collapse Strategy for a Raw Node Controller

- **Version:** 0.1.11
- **Date:** 2026-11-21
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose and scope

`uc-raw-node` is the raw node controller. Its only job is to produce a node that meets the raw node contract (the `RN-*` clauses) from `raw-node-input.yml` (`hostname`, `root_password_hash`, `initial_username`, `initial_password_hash`, `ssh_public_key`) and to write `confirmation.yml` keyed by hostname (timestamp, ip, ip6, user, sudo) for the orchestration controller's inventory. Everything after that (discover, verify, onboard, normalize and customize) belongs to the orchestration controller.

The platform taxonomy maps discovery sources and infrastructure targets, not creation mechanisms. Several entries overlap in how they actually build a node: AWS, GCP, Azure, Proxmox, libvirt, Incus, LXD and most VPS providers all accept cloud-init user-data. PXE, IPMI, USB sticks and custom APIs are delivery channels, not OS-level strategies.

To minimize complexity, the controller collapses the taxonomy into one payload, four delivery strategies and a transport registry, with discovery left to the orchestration controller. Adding a platform should mean adding a registry entry, not changing controller logic.

## Contract input

`raw-node-input.yml` holds everything the controller needs to know about the node itself. Everything about the platform comes from the registry instead.

| Field | Rule | Used for |
| :-- | :-- | :-- |
| `hostname` | A single lowercase DNS label: letters, digits and hyphens, 1 to 63 characters, not starting or ending with a hyphen | The node's hostname, the key of `confirmation.yml`, the instance name on platforms that name instances, and the node's directory under the controller's output and secrets paths |
| `root_password_hash` | A crypt hash such as `$y$...` or `$6$...`; plaintext is rejected | The root password |
| `initial_username` | A valid user name that is not `root` | The initial sudo user |
| `initial_password_hash` | A crypt hash; plaintext is rejected | The initial user's password |
| `ssh_public_key` | One OpenSSH public key line | The initial user's authorized key |

The controller checks every field before anything is created, and stops with a message naming the field that failed. Fields it does not use produce a warning rather than an error, so the input can carry information for other tools.

`hostname` is new in this version. It was implied before, since `confirmation.yml` is keyed by hostname, but no input field supplied it. The `RN-*` contract and uc-ventoy's generator, which share this input format, need the same field added, and the validator gains a check that the node's hostname matches it.

## The common payload

Every strategy ends by running the same thing: create the initial user, install the SSH key, set the root password hash, apply the baseline nftables ruleset, and report back. This is packaged once as `raw-node-firstboot`, the canonical payload. A strategy only answers one question: how does this payload reach the node and get executed exactly once?

Keeping one payload means the `RN-*` clauses are implemented in one place and tested once, and the validator can check the same outcome no matter how the node was built. The payload is delivered as either cloud-config user-data, an installer answer file, a baked image manifest, or a raw script pushed over an existing channel. Each strategy decides only the payload format; the transport delivers it.

## Delivery strategies and transport registry

| Strategy | How the payload runs | Typical targets |
|----------|---------------------|-----------------|
| `cloud_init` | Rendered as cloud-config user-data, executed by cloud-init on first boot | Cloud, VPS with user-data, Incus/LXD cloud images, Proxmox, libvirt, VMware |
| `installer` | Embedded in an installer answer file (Preseed, Kickstart, Subiquity autoinstall) and run as a late command or first-boot unit | Bare metal via uc-ventoy USB or PXE, VPS with custom ISO |
| `image` | Baked into a disk image or template, triggered by a first-boot unit | Air-gapped, high-throughput, immutable, rescue-mode `dd` deployments |
| `adopt` | Pushed over a channel that already exists (SSH, `incus exec`, qemu guest agent) and run once | VPS without user-data, containers without cloud-init, nodes handed over by someone else |
| Discovery | Not a creation strategy, handled by the orchestration controller's `00_discover.yml` | CMDB, DHCP, ARP, cloud inventory |

The `adopt` strategy exists so that SSH-only VPS hosts and plain container images are not forced into strategies that do not fit them.

Because `adopt` works on a system that already exists, it starts from whatever state that system is in. Before the payload is delivered, the target should be at a known baseline: a freshly created container, a freshly reinstalled provider template, or a plain OS image rather than one managed by a control panel. Where the controller cannot reset the target itself, the registry entry's notes say how a maintainer does it. The payload still asserts the contract state explicitly, so a leftover provider default is corrected or caught by the validator rather than assumed away.

Payload format and transport are strictly separated:

- **Payload format** is decided by the strategy: cloud-config user-data, an answer file, an image manifest, or a bare `raw-node-firstboot` script.
- **Transport** is how that format reaches the node: a NoCloud seed (ISO, VFAT `CIDATA` volume or local files), a provider metadata endpoint, a platform API, PXE, a Ventoy USB stick, SSH, or `incus exec`.

Transport is where platforms actually differ, so it is the pluggable part. Each transport is a small role, and the registry says which strategy and transport a platform uses.

The boundary between `installer` and `cloud_init` is deliberately blurred for Ubuntu. Subiquity takes its autoinstall configuration through cloud-init, and in most cases the simplest route is user-data on the NoCloud datasource <a id="cite-canonical-autoinstall"></a>[(Canonical, n.d.-a)](#ref-canonical-autoinstall). uc-ventoy's Ubuntu path is therefore `installer` strategy with a NoCloud seed transport. This is correct, and should not be "fixed" later by moving it to `cloud_init`.

## Registry and inventory

The platform registry and the Ansible inventory answer different questions. The inventory describes hosts that exist, so Ansible can reach them. The registry describes how to build a host on a given platform, and is not tied to any running instance. `confirmation.yml` is the hand-off point: the controller uses the registry to build a node, and the orchestration controller turns the resulting confirmation into inventory.

The registry's fields, its full contents, how it is layered per client, and the Ansible logic that consumes it are defined in [The Platform Registry](1-the-platform-registry-v0.1.5.md). That document is authoritative; this one only shows the outline.

## Controller routing flow

```mermaid
flowchart TD
 A[raw-node-input.yml] --> B{Resolve platform from registry}
 B -->|cloud_init| C[Render user-data]
 B -->|installer| D[Render preseed / ks / autoinstall]
 B -->|image| E[Render image manifest + firstboot unit]
 B -->|adopt| F[Stage raw-node-firstboot]

 C --> G[Deliver via transport]
 D --> G
 E --> G
 F --> G

 G --> H{Phone-home received before timeout?}
 H -->|Yes| I[Run raw_node_validator]
 H -->|No| J{Platform can destroy?}

 I --> K{Contract met?}
 K -->|Yes| L[Write confirmation.yml]
 K -->|No| J

 J -->|Yes| M[Destroy, optional fallback attempt]
 J -->|No| N[Mark quarantined and alert]

 classDef strat fill:#23233a,stroke:#6366f1,color:#818cf8,stroke-width:2px
 classDef proc fill:#1c2b24,stroke:#10b981,color:#34d399,stroke-width:2px
 classDef gate fill:#352b1c,stroke:#f59e0b,color:#fbbf24,stroke-width:2px
 class C,D,E,F strat
 class G,I,L,M,N proc
 class B,H,J,K gate
```

Reading the diagram: after delivery, the controller waits for the phone-home report. A report leads to validation, and a node that meets the contract gets its `confirmation.yml`. A missing report or a failed contract goes to the capability gate: destroyable platforms are destroyed (with at most one fallback attempt), and the rest are quarantined with an alert.

The first gate is a registry lookup, not capability detection. An optional probe (for example, checking whether an image ships cloud-init) can refine the choice, but the registry is the source of truth.

## Platform-to-strategy decision matrix

| Target platform | Primary strategy | Transport / datasource | Fallback |
| :-- | :-- | :-- | :-- |
| Incus or LXD, `/cloud` image variants | `cloud_init` | Incus API, `cloud-init.user-data` config key | `adopt` via `incus exec` |
| Incus or LXD, default image variants | `adopt` | `incus exec`, `incus file push` | `cloud_init` after switching to a `/cloud` image |
| Proxmox, libvirt | `cloud_init` | `nocloud` seed or `configdrive` | `installer` |
| VMware | `cloud_init` | `vmware` datasource (guestinfo) or `ovf` | `installer` |
| AWS, GCP, Azure, Oracle Cloud | `cloud_init` | Provider metadata endpoint (`ec2`, `gce`, `azure`, `oracle`) | `image` |
| VPS with API and user-data (DigitalOcean, Akamai/Linode, Vultr, UpCloud, Hetzner Cloud, Scaleway) | `cloud_init` | Provider datasource, see the VPS analysis | `installer` via rescue or custom ISO |
| VPS with SSH only | `adopt` | SSH | `installer` via custom ISO, if offered |
| VPS with a hosting-panel image (cPanel, CloudLinux) | Excluded | Reinstall a plain OS template, then treat as SSH only | Not applicable |
| Bare metal, modern | `installer` | uc-ventoy USB, PXE | `image` |
| Hosted dedicated or VPS in rescue mode | `image` | `dd` or `installimage` from the rescue system over SSH | `installer` via custom ISO |
| Bare metal, legacy or air-gapped | `image` | `dd`, `rsync` or DRBL from local media | `installer` |
| CMDB, DHCP, ARP, cloud inventory | Not a creation target | Orchestration controller `00_discover.yml` | Not applicable |

The datasource names above come from cloud-init's list of supported datasources, which includes VMware, OVF, NoCloud, ConfigDrive, LXD and the major clouds and VPS providers <a id="cite-canonical-datasources"></a>[(Canonical, n.d.-b)](#ref-canonical-datasources). "Shared hosting" is excluded: it does not provide a node.

## Issue analysis

This section works through specific problems and decides, for each, which strategy and transport handle it and what the controller must do differently. It replaces a generic provider interface: the differences between platforms are captured as decisions here and as data in the registry.

### VPS providers

"VPS" covers several quite different situations, and each one maps to a different strategy.

#### API with user-data

Most mainstream providers accept cloud-init user-data at creation time and expose it through a metadata endpoint. This is the `cloud_init` strategy with the provider API as transport, and it is the fastest path.

Issues to handle:

- **Provider defaults compete with the contract.** Provider images often create their own default user, place the account's SSH keys on root, set the hostname from the panel, and may ship `vendor-data` that runs alongside user-data. The payload must assert the contract state explicitly (user, root hash, key, hostname) rather than assume a blank image, and the validator must check for unexpected authorized keys.
- **Hostname is the confirmation key.** Because `confirmation.yml` is keyed by hostname, the controller sets the hostname in user-data and the validator confirms it, rather than trusting the provider's metadata name.
- **Provider firewalls are separate.** Many providers have their own network firewall. It is outside the `RN-*` contract, but the controller must make sure it does not block SSH or the phone-home call, otherwise a correct node looks failed.
- **Agents.** Some images include provider monitoring or guest agents. Their presence is recorded in `confirmation.yml` notes rather than removed, so the orchestration controller can decide in `20_normalize`.

#### SSH only

Budget providers and panel-based hosts often give a root password or key and nothing else. This is the `adopt` strategy with SSH as transport.

Issues to handle:

- **Unknown starting state.** The provider template is of unknown provenance. Where the panel allows it, reinstall the template immediately before adopting, so the starting state is at least fresh.
- **Credentials the provider knows.** The root password was issued by the provider. The payload replaces it with `root_password_hash`, which the contract already requires.
- **Host key trust.** The first SSH connection is trust-on-first-use. If the provider shows the host key fingerprint in its console, the controller compares it. Otherwise the risk is recorded in `confirmation.yml`.

#### Hosting-panel images

Some providers default to images built around a hosting control panel, such as cPanel on CloudLinux. These are not raw nodes: the panel manages its own users, services and firewall, and applying the contract's user, root and nftables changes on top of it risks conflicting with the panel or breaking it. The registry marks these images as excluded. Where the provider also offers a plain OS template, reinstall with that template and treat the node as SSH only.

#### Rescue mode or custom ISO

Some providers let you boot a rescue system or attach your own ISO. Hetzner, for example, provides a Debian-based rescue system with an `installimage` script that runs unattended when it finds an `/autosetup` file, and supports custom images <a id="cite-hetzner-installimage"></a>[(Hetzner Online, 2020)](#ref-hetzner-installimage). This path supports either the `installer` strategy (custom ISO with a NoCloud seed) or the `image` strategy (`dd` or `installimage` from rescue).

It is slower and needs console or rescue access, but it is the only VPS path where the controller, not the provider, decides what is on the disk. For clients where provenance and the ability to migrate matter, this should be the preferred path even when user-data is available.

#### Container-based VPS

Some low-cost "VPS" products are actually containers on a shared kernel (OpenVZ or LXC style). Kernel modules, and sometimes nftables, may not be available inside them, so the baseline firewall clause may be impossible to meet. The controller should detect this (through the registry entry, or by checking that `nft list ruleset` works) and fail with a clear "contract cannot be met on this platform" error rather than produce a node that looks compliant but is not.

#### Choosing among them

The controller does not choose a mode. The operator chooses one by choosing the registry entry, and each mode the controller should use on a provider has its own entry (for example, `hetzner_cloud` for user-data and `rescue_dd` for rescue mode). The registry's `vps_modes` field records which modes a provider offers, as information for maintainers; it does not affect routing.

When choosing, the recommended order is: rescue or custom ISO when the client's provenance requirements call for it, otherwise user-data, otherwise SSH adoption. Hosting-panel images are excluded, and container-based VPS products are rejected unless a contract waiver is defined.

### Containers on Incus and LXD

Images from the `images:` remote come in default and `/cloud` variants, and only the `/cloud` variants include cloud-init. Incus VMs also need either a working `incus-agent` or an extra cloud-init disk for the configuration to reach the guest <a id="cite-incus-cloudinit"></a>[(Linux Containers, n.d.)](#ref-incus-cloudinit).

Decisions:

- **`/cloud` variants** use `cloud_init` with the Incus API as transport.
- **Default variants** use `adopt` with `incus exec` and `incus file push`. There is no installer fallback, because containers do not run installers.
- **Address.** Incus reports the instance address through its API, so phone-home is optional here, but it is still used so that every strategy produces the same evidence.
- **Firewall inside unprivileged containers** may be restricted. As with container-based VPS, the registry records whether the baseline nftables clause applies.

### Local hypervisor VMs

Proxmox, libvirt and Incus VMs all accept a NoCloud seed or config drive, and this is the most predictable `cloud_init` path. The main issue is cleanup: the seed volume holds credentials (see credential exposure) and should be detached after the node passes validation.

### Bare metal with uc-ventoy or PXE

This is the `installer` strategy. uc-ventoy already renders the answer files on the workstation and stores only its output on the stick. The controller treats uc-ventoy as the transport for this case rather than reimplementing it.

The issues specific to this case are that the controller cannot see the machine boot, does not know its address, and cannot destroy it. Phone-home is therefore mandatory here, and failure handling ends in quarantine, not teardown.

### Air-gapped and immutable targets

This is the `image` strategy with a local-media transport. The payload is baked into the image and triggered by a first-boot unit that removes itself after running. With no network path back to the controller, phone-home writes its report to local media (or a known path for later collection), and the validator runs when the orchestration controller can reach the node.

Rescue-mode deployment on hosted machines also uses the `image` strategy, but over SSH to the rescue system. It needs a network and is a separate registry entry from the air-gapped case.

### Finding the node

`wait_for_boot` in earlier drafts assumed the controller already knew the node's IP. That is true for Incus and cloud APIs, but not for bare metal or SSH-handed-over VPS hosts.

Every strategy now ends the payload with a phone-home call. cloud-init has a `phone_home` module that posts data, including the SSH host public keys, instance ID and hostname, to a URL after boot <a id="cite-canonical-phonehome"></a>[(Canonical, n.d.-c)](#ref-canonical-phonehome). The `installer`, `image` and `adopt` payloads send the same POST themselves. Sending the host keys also solves trust-on-first-use for the validator's SSH connection.

The report maps directly onto `confirmation.yml`. Each attempt includes a one-time token in the payload, so the receiver can reject unexpected reports.

A receiver reachable from the internet will see forged and replayed requests, so it must:

- **Accept reports only over TLS**, so the token and host keys cannot be read or altered in transit.
- **Treat each token as single-use and short-lived.** A token is bound to one attempt and one expected hostname, expires when the attempt times out, and is rejected after its first use.
- **Not trust the report on its own.** The validator still connects to the node, checks that the SSH host key matches the reported one, and checks the contract itself. A forged report can at worst cause a failed validation, never a confirmation.

There is one practical issue for VPS targets: a controller on a workstation behind NAT cannot receive a callback from the internet. The options are a small, always-on receiver on a host the client controls, or polling the provider API for the address. The receiver is preferred, since it works the same way for every target.

### Failure and teardown

Earlier drafts said teardown was identical across providers. It is not. The registry carries a `can_destroy` flag per platform:

- **Destroyable** (cloud, VPS with API, Incus, local hypervisors): destroy the node, keep the logs and the failed artifacts, and optionally make one fallback attempt.
- **Not destroyable** (bare metal, SSH-adopted VPS, nodes handed over by someone else): mark the node as quarantined in a failure record, alert, and never retry automatically.

The error report always names the `RN-*` clause that failed, not the delivery mechanism.

### Fallback selection

Fallback is chosen in one of two ways, never silently:

- **Before delivery**, when a probe or registry entry shows the primary strategy cannot work (for example, an Incus image without cloud-init). This is automatic and logged.
- **After failure**, only for destroyable platforms, and only once. On non-destroyable platforms it is a manual decision.

In the registry, a fallback is a pointer to another registry entry, never a combined transport such as "API or SSH", so that every attempt has exactly one strategy, one transport and one set of capability flags. Fallback is limited to one hop: the target entry may not have a fallback of its own, which makes loops impossible.

### Credential exposure

The payload carries password hashes and an SSH key, and every transport leaves a copy somewhere:

- **Metadata endpoints.** On clouds such as AWS, user-data stays readable from inside the instance through the metadata service. Instances should be launched requiring IMDSv2 (token-based requests) <a id="cite-aws-imdsv2"></a>[(Amazon Web Services, n.d.)](#ref-aws-imdsv2). Hashes are acceptable in user-data; plaintext secrets are not.
- **Seed media.** Detach NoCloud seed volumes and config drives after validation.
- **USB and PXE.** uc-ventoy output on the stick and PXE answer files should be treated as credentials and removed or rotated after the install batch.
- **Controller staging.** The rendered payload and the phone-home token are staged on the controller host only in the secrets path, `<raw_node_secrets_path>/<hostname>/` (by default `~/.secrets/uc-raw-node/<hostname>/`, outside the repository), in directories with mode 0700 and files with mode 0600. They are deleted after delivery, or once validation passes where the transport needs them until then, and by failure handling.
- **Payload cleanup.** `raw-node-firstboot` deletes its own staged copy and the phone-home token after running.

### Init systems and degraded paths

The validator detects the init system with `cat /proc/1/comm` (or `readlink /proc/1/exe`) rather than `ps -p 1 -o comm=`, which fails on BusyBox. Checks are conditional: systemd units and timers are only validated if systemd is PID 1.

When cloud-init is missing and the payload must schedule itself, the degraded paths have preconditions that must be checked rather than assumed: `/etc/rc.local` on systemd needs `rc-local.service`, and `cron @reboot` needs a cron daemon installed and enabled. A systemd oneshot unit that disables itself is preferred wherever systemd is present.

For networking, the validator continues to read `ip -4 addr`, `ip -6 addr`, `ip route` and `/etc/resolv.conf` directly, without assuming a network manager.

### Firewall scope

The raw node contract only asks for the baseline nftables ruleset. The controller ensures that baseline is present and that SSH stays reachable. Foomuuri management, and any richer policy, belongs to the orchestration controller's `20_normalize` stage. This keeps the raw node layer minimal and avoids a firewall change locking the controller out before `confirmation.yml` is written.

## Ansible implementation pattern

A single entry point, `build.yml`, runs the following steps; `validate.yml` runs only the checks, and `destroy.yml` tears a node down by hostname. The layout is defined in *Raw Node Controller Layout Design*. The exact registry and dispatch tasks are in [The Platform Registry](1-the-platform-registry-v0.1.5.md); the input checks are in `load_input.yml`.

- Load the registry layers (base registry, then any client layers) and validate every entry and fallback in the merged registry.
- Load `raw-node-input.yml` and check every field.
- Assert that `target_platform` exists in the registry, then resolve its entry with defaults applied.
- Resolve the delivery strategy, allowing an explicit `raw_node_strategy_override`.
- Assert that the entry is usable: not excluded, a known strategy, a known transport, a valid firewall clause.
- Inside one block: render `raw-node-firstboot`, render the strategy's artifacts, deliver through the transport role, wait for the phone-home report, run `raw_node_validator`, and write `confirmation.yml`.
- On any failure, a rescue section handles the outcome according to the entry's `can_destroy` and `fallback` values.

A registry entry is plain data, for example:

```yaml
incus_container_default:
  strategy: adopt
  transport: incus_exec
  can_destroy: true
  reports_address: true
  firewall_clause: check
```

## Why this solves the complexity problem

- **One payload:** the `RN-*` clauses are implemented once, in `raw-node-firstboot`, and validated once.
- **Single routing decision:** the registry entry for `target_platform` sets strategy and transport. There are no nested conditionals and no platform-specific playbook forks.
- **Differences are data:** per-platform behaviour (can it be destroyed, does it report an address, does the firewall clause apply) lives in the registry, informed by the issue analysis, not in code.
- **Artifact isolation:** generation, delivery and verification stay separate. A broken Preseed generator does not break the cloud-init path.
- **Discovery decoupled:** network, DHCP, ARP and CMDB sources feed the orchestration controller's discovery stage, not this controller.
- **Predictable failure:** failures name the `RN-*` clause that failed, and the response (destroy or quarantine) follows from the registry, not from improvisation.

## Should IaC shims be a strategy?

**Short answer: no. They should sit outside the controller.**

### Why IaC as a core strategy clouds the waters

- **Scope:** IaC tools manage infrastructure lifecycle, multi-region layouts and drift. `uc-raw-node` only cares about getting one node to meet the contract. Mixing the two widens the controller's responsibility without adding value to that job.
- **Competing state:** IaC tools keep authoritative state with plan and apply cycles. The controller keeps only a small attempt record (which nodes it created, which attempt is in flight) so it can retry and clean up safely. Two sources of truth for the same node invite conflict.
- **Coupling:** tying the controller to one IaC ecosystem locks in its language and provider plugins, which works against the goal of infrastructure that can be migrated over time.

### Recommended boundary: IaC as an external caller

IaC stacks call the controller, not the other way round.

```text
[IaC stack] → [Terraform/OpenTofu/Pulumi module] → [uc-raw-node CLI or role] → [platform API or transport]
```

A thin **IaC adapter**, packaged separately, can:

- Read Terraform or OpenTofu outputs, or Pulumi stack references
- Translate them into `raw-node-input.yml` and a `target_platform` key
- Invoke the controller
- Return the contents of `confirmation.yml`, or the failure record, as IaC outputs

## Controller architecture recommendation

- **Core controller:** one payload, four strategies (`cloud_init`, `installer`, `image`, `adopt`), transport roles, and the platform registry. No IaC logic and no discovery inside.
- **Platform registry:** one entry per platform with strategy, transport, datasource, `can_destroy`, `reports_address`, fallback, status and any contract caveats. VPS entries also record which modes (user-data, SSH only, rescue or custom ISO) the provider supports.
- **Phone-home receiver:** a small endpoint on a host the client controls, used by every strategy.
- **Validation pipeline:** universal. Init system detection, baseline firewall and `RN-*` checks run identically regardless of delivery method.
- **IaC adapter (optional):** a separate package that maps IaC outputs to controller inputs.

## Open questions

- Is `adopt` the right name, or does `bootstrap` read better next to the other three?
- Should post-failure fallback exist at all in the first release, or should every fallback be manual until the strategies are proven?
- Where does the phone-home receiver live for Vishpala clients: on the client's infrastructure, or on a small shared relay?
- Should container-based VPS and unprivileged containers get a defined contract waiver for the firewall clause, or be rejected outright?
- Is the `image` strategy needed for the first release, or can it wait until an air-gapped client needs it?

## Changes

### From v0.1.10 to v0.1.11

- Named `build.yml` as the entry point in the Ansible implementation pattern, replacing `roles/raw_node_controller/tasks/main.yml`, after the controller layout migration (*Raw Node Controller Layout Design* v0.1.8).
- Added the secrets path to credential exposure as the only place on the controller where the payload and token are staged.
- Replaced the artifacts directory with the node's output and secrets directories in the contract input table, and pointed the registry links to v0.1.5.

### From v0.1.9 to v0.1.10

- Added `hostname` to the contract input, and a "Contract input" section with the rule for each field and how the controller checks them.
- Added input checking to the Ansible outline, and pointed the registry links to v0.1.4.

### From v0.1.8 to v0.1.9

- Added the requirement that `adopt` starts from a known baseline.
- Added phone-home receiver security: TLS, single-use short-lived tokens bound to an attempt, and validation that does not rely on the report alone.
- Added a caption explaining how to read the routing diagram.

### From v0.1.7 to v0.1.8

- Rewrote "Choosing among them" so that the operator chooses a VPS mode by choosing the registry entry, and `vps_modes` is described as metadata that does not affect routing.
- Stated that fallback is limited to one hop.
- Updated the Ansible outline to include registry validation, and pointed the registry links to v0.1.3.

### From v0.1.6 to v0.1.7

- Set the header version to 0.1.7 to match the filename (the v0.1.6 header said 0.2.0), and wrote the metadata as a list instead of relying on trailing-space line breaks. License unchanged.
- Replaced the em dashes in the scope paragraph.
- Corrected the sentence that said each strategy handles only the transport layer: the strategy decides the payload format, and the transport delivers it.
- Removed the "new in this version" wording for `adopt`.
- Added the "Registry and inventory" section and made [The Platform Registry](1-the-platform-registry-v0.1.2.md) the single authority for registry fields, contents and consumer logic. The Ansible section now outlines the steps instead of duplicating the code.
- Added hosting-panel images (excluded) and split hosted rescue-mode deployment from air-gapped deployment, in both the matrix and the issue analysis.
- Stated that a fallback is a pointer to another registry entry, never a combined transport.
- Restored the in-text citations and the Citation Anchor Pairs in References.
- Fixed "DRBl" to DRBL.

### From v0.1.5 to v0.1.6

- Added the metadata block, changed the title to title case, and merged the strategy and transport sections under one heading.

### From v0.1.4 to v0.1.5

- Added the common `raw-node-firstboot` payload and the `adopt` strategy.
- Split payload format from transport, and replaced `defaults/detection.yml` with a platform registry.
- Replaced the provider-interface idea with an issue analysis covering VPS providers, containers, local VMs, bare metal, air-gapped targets, node location, failure, fallback, credentials, init systems and firewall scope.
- Replaced `wait_for_boot` with phone-home, and made teardown depend on whether the platform can be destroyed.
- Corrected the VMware datasource, removed shared hosting, and removed the installer fallback for containers.
- Fixed the Ansible snippet (indentation, registry lookup, failure handling) and unified the validator name as `raw_node_validator`.
- Moved Foomuuri management to the orchestration controller.
- Removed chat residue and paste artifacts, and added references.

## References

<a id="ref-aws-imdsv2"></a>Amazon Web Services. (n.d.). *Modify instance metadata options for existing instances*. Amazon Elastic Compute Cloud User Guide. https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-existing-instances.html
[Return to citation](#cite-aws-imdsv2)

<a id="ref-canonical-autoinstall"></a>Canonical. (n.d.-a). *Automated server installs*. Ubuntu Discourse. https://discourse.ubuntu.com/t/automated-server-installs/16612
[Return to citation](#cite-canonical-autoinstall)

<a id="ref-canonical-datasources"></a>Canonical. (n.d.-b). *Datasources*. cloud-init documentation. https://docs.cloud-init.io/en/latest/reference/datasources.html
[Return to citation](#cite-canonical-datasources)

<a id="ref-canonical-phonehome"></a>Canonical. (n.d.-c). *Phone home: Post data to remote host*. cloud-init documentation. https://docs.cloud-init.io/en/24.4/reference/yaml_examples/phone_home.html
[Return to citation](#cite-canonical-phonehome)

<a id="ref-hetzner-installimage"></a>Hetzner Online. (2020, May 18). *Installimage*. Hetzner Docs. https://docs.hetzner.com/robot/dedicated-server/operating-systems/installimage/
[Return to citation](#cite-hetzner-installimage)

<a id="ref-incus-cloudinit"></a>Linux Containers. (n.d.). *How to use cloud-init*. Incus documentation. https://linuxcontainers.org/incus/docs/main/cloud-init/
[Return to citation](#cite-incus-cloudinit)
