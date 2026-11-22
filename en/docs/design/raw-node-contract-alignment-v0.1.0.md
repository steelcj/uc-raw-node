# Raw Node Contract Alignment

- **Version:** 0.1.0
- **Date:** 2026-11-21
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose and scope

uc-raw-node is a raw node producer. The clauses it must meet are not its own: they are the raw node contract, version 0.3.1, in uc-contracts (`en/docs/node-onboarding-pipeline/1-raw-node-egress/uc-raw-node-contract.md`, commit `3f90d9e`). This document does not restate or change any clause. It decides how uc-raw-node meets the contract, how its validator checks it, and what has to change in uc-raw-node's code and documents for that, starting with priority 1: a Debian 13 container on a local Incus server (`incus_container_default`, `adopt` strategy, `incus_exec` transport).

It replaces the placeholder promise in the README and the layout design that `payload.yml` and `raw_node_validator` wait for "the `RN-*` clauses to be pinned down". They are pinned down already, in uc-contracts, and uc-ventoy implements them.

## What already exists

Three pieces of work answer most of the question before uc-raw-node writes any code.

- **The contract,** 0.3.1 in uc-contracts. Version 0.3.1 changed wording only from 0.3.0, so a node built to either meets the same clauses. It defines the shared parameters, the clauses in five groups (RN-NET, RN-ACC, RN-SSH, RN-FW, RN-REP), and a confirmation that the node measures and writes itself at `/var/lib/raw-node/confirmation.yml`.
- **uc-ventoy, the first producer,** at commit `5ed7bb8` (baseline 0.4.0, contract 0.3.0). Its `shared/` folder holds the node files every target installs: `bin/raw-node-firstboot`, `bin/raw-node-report`, `systemd/raw-node-firstboot.service`, `systemd/foomuuri-raw-node.conf`, `ssh/10-local-auth.conf` and `foomuuri/00-raw-node.conf.j2`. Its `en/docs/contracts.md` maps every clause to how it is met, and lists "Checks on an installed node", a ready checklist for a validator.
- **The Incus spike,** `en/docs/incus/spike-incus-container-validation-v0.2.19.md` in this repository. It installed uc-ventoy's node files in an unprivileged Debian 13 Incus container (`images:debian/13/cloud`, through cloud-init) and met every clause, RN-FW-04 included once the Foomuuri drop-in is on both `foomuuri.service` and `foomuuri-boot.service`. No clause needed a container exception.

## Where uc-raw-node differs from the contract today

uc-raw-node's documents were written against an earlier picture of the raw node. These are the places they disagree with contract 0.3.1:

| Topic | uc-raw-node today | Contract 0.3.1 |
| :-- | :-- | :-- |
| Contract input | Five fields: `hostname`, `root_password_hash`, `initial_username`, `initial_password_hash`, `ssh_public_key` | Shared parameters also include `ssh_port` (default 22) and `ssh_sources` (default empty, meaning any). uc-ventoy also accepts an optional `password_batch`. |
| Who writes the confirmation | The controller writes `records/<hostname>/confirmation.yml` with `timestamp`, `ip`, `ip6`, `user` and `sudo`, from the transport's address report | The node writes `/var/lib/raw-node/confirmation.yml` itself, measured on the node, with 14 fields under the hostname, including `ssh_host_keys`, `interfaces` and `machine_id` (RN-REP-01) |
| Firewall | The strategy document says the payload applies "the baseline nftables ruleset" and leaves Foomuuri to the orchestration controller | The firewall manager is the producer's choice and is reported in `firewall`. uc-ventoy uses Foomuuri, with one file, `/etc/foomuuri/00-raw-node.conf`. |
| SSH | The backend contract (v0.2.1) says SSH accepts key and password authentication | Key only (RN-SSH-03). The initial password is for the console (RN-ACC-06) and sudo (RN-ACC-04). |
| Clause names | The backend contract refers to RN-01 to RN-12 | Those are uc-ventoy's own baseline requirements. The contract's clauses are RN-NET-01, RN-ACC-01 and so on. |
| The payload | Described as uc-raw-node's own `raw-node-firstboot`, which creates the user, sets passwords, applies the firewall and reports | uc-ventoy's `raw-node-firstboot` only sets the hostname suffix and writes the report. Users, passwords, packages and the firewall are set up by the answer file before first boot. |
| Reading the confirmation | Not specified | A consumer must read every value as a string and convert the booleans and `ssh_port` itself, because YAML 1.1 parsers, Ansible included, change some values silently |

## Decisions

### The contract version

uc-raw-node targets contract 0.3.1. A node reports the versions in its `/etc/raw-node/raw-node.conf`, which `raw-node-adopt` writes, so uc-raw-node decides what its nodes report, whatever uc-ventoy commit its node files come from:

- `contract` is `0.3.1`.
- `baseline` is uc-raw-node's own, since the contract defines it as the producer's baseline version. The contract has no field naming the producer, so the value carries the name: `uc-raw-node/<release>`, for example `uc-raw-node/0.4.0`, which cannot be mistaken for uc-ventoy's `0.4.0`.

The validator accepts contract `0.3.0` and `0.3.1`, which differ in wording only, and nothing older, so it can also check a node uc-ventoy built.

### One set of node files

uc-raw-node installs uc-ventoy's `shared/` files byte for byte, as the backend contract's RB-03 already requires. It never keeps its own edited copy. The files are vendored into `files/raw-node/` at a pinned uc-ventoy commit, with a `MANIFEST` listing the commit and each file's SHA-256 and mode on the node. `tools/check.sh --fast` checks the manifest, so a hand edit fails at the next commit. Updating means copying from a newer uc-ventoy commit and updating the manifest, deliberately, in its own commit.

Vendoring rather than a git submodule keeps the repository self-contained and its checks simple. The cost is a copy to keep in step, which the manifest makes visible.

### The adopt payload

For `adopt`, the payload is a new script, `raw-node-adopt`, kept in uc-raw-node because it is how this strategy delivers the node files, the role the answer file plays for uc-ventoy. Run once as root on a fresh Debian 13 instance, it does what uc-ventoy's Debian answer file and `late_command` do:

- install `openssh-server`, `sudo`, `python3` and `foomuuri`;
- set the hostname to `hostname` from the contract input;
- set the root password from `root_password_hash`;
- create `initial_username` with `initial_password_hash`, add it to `sudo`, and install `ssh_public_key` as its only file in `.ssh/`;
- install the node files from `files/raw-node/` with their manifest modes, `00-raw-node.conf` rendered from its template with `ssh_port` and `ssh_sources`, and `20-raw-node-port.conf` for `ssh_port`;
- write `/etc/raw-node/raw-node.conf`, with `RAW_NODE_CONTRACT=0.3.1`, `RAW_NODE_BASELINE=uc-raw-node/<release>`, `RAW_NODE_USER`, and `RAW_NODE_PASSWORD_BATCH` when `password_batch` is given;
- mask `nftables.service`, enable `foomuuri.service` and `raw-node-firstboot.service`.

It does not start the firewall or write the confirmation. The transport restarts the instance afterwards, so that the firewall comes up before the network as it would at any boot (RN-FW-04), and `raw-node-firstboot` runs at a real first boot and writes the confirmation. The restart also proves RN-FW-04 on the boot that produced the confirmation.

The Foomuuri drop-in goes on both Foomuuri units only for images with cloud-init, where the spike found the ordering cycle. `images:debian/13` has no cloud-init, so the packaged units are used unchanged, as on uc-ventoy's Debian 13 target. The validator checks RN-FW-04 either way.

The script follows the payload output rules in the layout design. The hashes and the key are not in its arguments: `raw-node-adopt` reads them from a `0600` file staged beside it in the secrets path, which it deletes before the restart, and passes the hashes to `chpasswd -e` and `usermod -p` on standard input or in a file, never on a command line. It never runs with `set -x`.

### The report is the node's confirmation

The node's own `/var/lib/raw-node/confirmation.yml` is the report. For transports that can reach inside the instance, `wait_phone_home.yml` waits until that file exists and fetches it through the transport: for Incus, with `incus file pull`. This replaces `address.yml` as the transport's report step, since the addresses are in the confirmation's `interfaces`. The phone-home receiver remains the route for platforms the controller cannot reach inside, and it carries the same file.

The fetched file is kept as `reports/<hostname>/confirmation.yml` until validation passes. `write_confirmation.yml` then copies it, byte for byte, to `records/<hostname>/confirmation.yml`. The controller adds nothing to it and removes nothing. Its own facts about the attempt stay in `attempt.yml`. The five-field confirmation is retired.

The orchestration controller therefore receives exactly what the contract defines, the same file a uc-ventoy node shows at its console. It finds the address in `interfaces`, the user in `user`, and trusts the node through `ssh_host_keys`, as the contract's Host keys section describes.

### Reading the confirmation

The controller reads the confirmation as the contract requires a consumer to: every value as a string, with the booleans and `ssh_port` converted by the controller. Ansible's `from_yaml` uses a YAML 1.1 loader that turns a timestamp into a datetime and some MAC addresses into integers, so the controller does not use it for the confirmation. A small filter plugin, `filter_plugins/raw_node_confirmation.py`, loads the file with PyYAML's `BaseLoader` and converts the seven typed fields. The validator and `write_confirmation.yml` use only that filter.

### The validator

`raw_node_validator` checks the contract, not the payload. It runs after the restart and the report, and works in three parts. Every check that fails names its clause, which becomes the failure record's `clause`.

#### The confirmation

The confirmation parses with the filter, its only top-level key is `hostname`, every field in the contract's table is present with the right type, and:

- `contract` is `0.3.0` or `0.3.1`;
- `user` is `initial_username`, and `sudo` is true;
- `sudo_nopasswd` is false (RN-ACC-07) and `ssh_password_auth` is false (RN-SSH-03);
- `ssh_port` is the input's `ssh_port`;
- `firewall_active` is true;
- `ssh_host_keys` is not empty;
- at least one interface holds an address.

#### Inside the node, through the transport

These are uc-ventoy's "Checks on an installed node", run with `incus exec`:

| Clause | Check |
| :-- | :-- |
| RN-NET-01 | `hostnamectl --static` is `hostname`, and not the image's default |
| RN-ACC-01 | The home directory holds only `.ssh/authorized_keys` and the files `/etc/skel` provides |
| RN-ACC-05 | `passwd -S root` reports `P`, and `sshd -T` reports `permitrootlogin no` |
| RN-ACC-07 | No non-comment line in `/etc/sudoers`, `/etc/sudoers-rs` or `/etc/sudoers.d/*` contains `NOPASSWD` or `!authenticate` |
| RN-SSH-01 | `ss -ltnp` shows sshd on `ssh_port` |
| RN-SSH-03 | `sshd -T` reports `pubkeyauthentication yes`, and `no` for password, keyboard-interactive and empty-password authentication |
| RN-FW-01 | `nft list tables` shows one table, and `iptables-legacy-save` has no rules or does not exist |
| RN-FW-02 | `nftables.service` is masked, and the one table belongs to the reported `firewall` |
| RN-FW-04 | In this boot, the firewall unit became active before `network-pre.target`, and `network-pre.target` before the network service, read from activation times as in the spike |
| RN-REP-01 | The file is mode `0644` and readable by `initial_username` |
| Host keys | Each `/etc/ssh/ssh_host_*_key.pub`'s fingerprint is in `ssh_host_keys`, one entry per key |

#### From the controller host

These need a network path from the controller host to the node:

| Clause | Check |
| :-- | :-- |
| Host keys | `ssh-keyscan` of the node's address, fingerprinted with `ssh-keygen -l`, matches `ssh_host_keys` exactly. This is the trust step the contract gives ingress, done once more by the producer. |
| RN-ACC-02 | `ssh -o PreferredAuthentications=publickey` as `initial_username` with the key succeeds |
| RN-SSH-02 | That login works on an address from `interfaces` |
| RN-SSH-03 | Password and keyboard-interactive logins, for `initial_username` and `root`, are refused without a prompt |
| RN-FW-03 | A listener started inside the node with `systemd-run` on a port the firewall does not open answers from inside and is not reachable from the controller host, while SSH is; ping answers |

When the controller host is not inside `ssh_sources`, it cannot run these. The validator then fails with a message saying so, rather than skipping them, since a node the controller could not reach has not been shown to meet RN-SSH-02.

#### Clauses the controller cannot check

uc-raw-node never holds `initial_password`. The contract gives it to ingress and the producer only its hash. Three clauses therefore cannot be fully checked here, and the validator reports how far it got for each:

| Clause | What the validator checks instead |
| :-- | :-- |
| RN-ACC-04, sudo with the password | `sudo -l -U initial_username`, as root, grants root, RN-ACC-07 holds, and `passwd -S initial_username` reports `P` |
| RN-ACC-06, console login with the password | `passwd -S initial_username` reports `P`, and a getty is enabled on the console |
| RN-ACC-08, password length | Not checkable from a hash. Met by procedure, as in uc-ventoy. |

These are recorded as `checked_by_proxy` in `reports/<hostname>/validation.yml`, so that ingress knows they still need the real check, which its `05_verify` can make because it holds the password.

### The contract input

`load_input.yml` accepts `ssh_port`, `ssh_sources` and `password_batch` as optional fields, with the defaults and rules in uc-ventoy's `raw-node-input.example.yml`, so that one input file serves both producers. `hostname` stays uc-raw-node's own field. The contract does not need it, because RN-NET-01 only asks that the hostname is set and is not the default, and the strategy document's statement that the contract and uc-ventoy need it too is withdrawn. `load_input.yml` refuses a `hostname` ending in `-vt`, because uc-ventoy's `raw-node-firstboot` appends a MAC suffix to such names at first boot, and the node would then report a hostname other than the one the controller asked for.

### Priority 1 stays on adopt

Priority 1 stays `incus_container_default`: `images:debian/13` without cloud-init, the `adopt` strategy and the `incus_exec` transport, which the controller already builds and tests. The spike's route, `images:debian/13/cloud` through cloud-init, is the natural second Incus entry, `incus_container_cloud`. It is proven to meet the contract, but it needs the `cloud_init` strategy and the Foomuuri drop-in on both units.

No container exception is needed. The registry's `firewall_clause` for `incus_container_default` is `applies`.

## Changes this needs

| Where | Change |
| :-- | :-- |
| `files/raw-node/` | New: uc-ventoy's `shared/` files at a pinned commit, with `MANIFEST` |
| `templates/` | `raw-node-adopt.j2` and its input file, replacing the planned `raw-node-firstboot.j2` |
| `tasks/load_input.yml` | `ssh_port`, `ssh_sources`, `password_batch` |
| `tasks/payload.yml` | Renders `raw-node-adopt` and its input file into the secrets path, replacing the placeholder |
| `roles/raw_node_transport_incus_exec` | Pushes and runs `raw-node-adopt`, restarts the instance, and gains `tasks/report.yml`, which waits for and fetches the node's confirmation, in place of `address.yml` |
| `tasks/wait_phone_home.yml` | Calls the transport's `report.yml` and keeps the fetched file |
| `tasks/write_confirmation.yml` | Copies the validated confirmation to `records/` unchanged |
| `filter_plugins/raw_node_confirmation.py` | New: string-safe reading of the confirmation |
| `roles/raw_node_validator` | The checks above, replacing the placeholder |
| `tools/check.sh` | Checks `files/raw-node/MANIFEST` in `--fast` |
| Strategy document, v0.1.12 | The confirmation is the node's; the payload is uc-ventoy's node files plus a strategy's delivery step; the firewall manager is the producer's choice; the `hostname` note withdrawn |
| Platform registry, v0.1.6 | `firewall_clause: applies` for Incus containers, with the spike as evidence |
| Backend contract, v0.3.0 | Clause references moved to contract 0.3.1's identifiers, key-only SSH, the input's optional fields |
| Layout design, v0.1.12 | The report step and its transport obligation (`report.yml`), `files/raw-node/`, the filter plugin, the validator's structure and `validation.yml`, the restart after delivery |
| README | Status, contract input, and links to this document and to uc-contracts |

The test suite gains a stand-in for the node's side: the stand-in Incus client must be able to serve a confirmation file in the contract's format, including values that YAML 1.1 misreads, so the filter is tested on them. The real-host run builds a Debian 13 container that meets the contract, which makes it the first real raw node from uc-raw-node.

## Observations for uc-contracts

- **Clauses a producer cannot check.** A producer never holds `initial_password`, so it can check RN-ACC-04 and RN-ACC-06 only by proxy, and RN-ACC-08 not at all. That is a consequence of the contract's design, not a defect. The contract could say so, so that every producer reports these the same way.
- **uc-ventoy's version.** uc-ventoy builds nodes that report contract `0.3.0`, while the contract is at 0.3.1. The change is wording only, so nothing breaks, but uc-ventoy's `CONTRACT_VERSION` could move to `0.3.1` at its next build.

## Open questions

- **Vendoring or a submodule** for uc-ventoy's node files. This document proposes vendoring with a manifest.
- **Where `raw-node-adopt` lives.** It is proposed for uc-raw-node. If uc-ventoy ever gains an adopt-style target, it could move to uc-ventoy's `shared/` with the other node files.
- **The baseline value.** `uc-raw-node/<release>` puts the producer's name in a field the contract calls a version. It is a string either way, but uc-contracts might prefer a separate `producer` field at its next minor version.
- **The phone-home receiver's payload.** This document makes the node's confirmation the report for every route. The receiver, when it is built, carries that file, and the strategy document's one-time token is sent alongside it.

## Changes

### v0.1.0

- First version: uc-raw-node aligned with raw node contract 0.3.1, reusing uc-ventoy's node files, a new adopt payload, the node's own confirmation as the report and the hand-off, a string-safe reader, the validator's checks by clause, and the list of changes to code and documents.
