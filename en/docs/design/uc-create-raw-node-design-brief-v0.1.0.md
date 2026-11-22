# uc-create-raw-node Design Brief

- **Version:** 0.1.0
- **Date:** 2026-11-22
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose

This brief is the starting point for the next design of uc-raw-node, the raw node controller. It records only what was settled on 2026-11-22, and replaces every earlier design document wherever they disagree. The first goal is a Debian 13 container on a local Incus server that meets the raw node contract.

## The contract is the only link

uc-raw-node builds nodes that meet the raw node contract, version 0.3.1, in uc-contracts (`en/docs/node-onboarding-pipeline/1-raw-node-egress/uc-raw-node-contract.md`). The contract is the only thing uc-raw-node shares with any other producer or consumer. uc-raw-node does not copy files from, depend on or refer to uc-ventoy or any other producer. Nodes from different producers are interchangeable because each meets the contract, not because they share code.

When a node meets the contract, uc-raw-node hands it to the orchestration controller.

## The node definition

The only input defined outside the controller describes the node, and nothing about where it is built:

| Field | Required | Rule |
| :-- | :-- | :-- |
| `hostname` | Yes | One lowercase DNS label, 1 to 63 characters, not ending in `-vt` |
| `root_password_hash` | Yes | Crypt hash, never plaintext |
| `initial_username` | Yes | Valid user name, not `root` |
| `initial_password_hash` | Yes | Crypt hash of a password of at least 15 characters (RN-ACC-08) |
| `ssh_public_key` | Yes | One OpenSSH public key line |
| `ssh_port` | No, default 22 | Integer from 1 to 65535 |
| `ssh_sources` | No, default any | IPv4 or IPv6 addresses or networks, host bits refused |
| `password_batch` | No | Letters, digits, `.`, `-`, `_`, at most 64 |

No value may contain a single quote or a newline.

The platform is chosen separately, per build, by the operator or by calling logic:

```sh
ansible-playbook build.yml -e @$HOME/.secrets/uc-raw-node/inputs/deb13-ic-01.yml \
  -e target_platform=incus_container_default
```

Platform settings, such as the Incus project, come from the registry, a client layer or `-e`, never from the node definition.

## What Ansible needs, and what the contract gives

Ansible needs an address, an SSH server, a user it can log in as with a key, and Python on the node. To change the system it needs privilege escalation, normally `sudo`.

| Ansible needs | The contract gives the orchestration controller |
| :-- | :-- |
| An address | `interfaces` in the confirmation |
| An SSH server | RN-SSH-01, on `ssh_port` |
| A user and key | RN-ACC-02, `initial_username` with `ssh_public_key` |
| `sudo` | RN-ACC-04, with the initial password, which the orchestration controller holds |
| Python | Reported, not promised |

The orchestration controller connects as `initial_username` with the key and becomes root with the initial password. Root cannot log in over SSH (RN-ACC-05), and no sudoers rule is passwordless (RN-ACC-07).

uc-raw-node never holds the initial password, only its hash, so it cannot use that `sudo`. It builds the node through the platform's own root channel instead, and hands over a node where `sudo` requires the password.

## The split

### What the transport does

The transport is the only part that depends on the platform. It configures nothing inside the node.

| Job | Incus |
| :-- | :-- |
| Create and destroy the instance, with the ownership marker | `incus launch`, `incus delete` |
| Give Ansible a root connection | The `community.general.incus` connection plugin, which runs tasks through `incus exec` |
| Find the address | `incus list` |
| Read the host keys through a trusted channel | `incus exec` |

A later VPS transport gives Ansible root SSH with a key the provider injects at creation, and finds the address and host keys through the provider's API.

### What plain Ansible does

Everything else runs over the transport's root connection, with ordinary roles and modules that behave the same on every platform. Every step is idempotent, so a build can be run again and converges instead of repeating.

## Order of operations

1. **Reach the node** (localhost). The transport creates or finds the instance, adds it to the inventory with its root connection, and reads its address and host keys.
2. **Bootstrap.** `robertdebock.bootstrap` installs Python and `sudo`. Facts are gathered only after this.
3. **Package sources.** `robertdebock.epel`, on the RHEL family only, where Foomuuri comes from EPEL. Nothing to do on Debian and Ubuntu.
4. **Packages.** `openssh-server` and `foomuuri`.
5. **Accounts.** The root password, and the initial user with its password hash, key and `sudo` group membership.
6. **Firewall.** Foomuuri rules from `ssh_port` and `ssh_sources`, `nftables.service` masked, Foomuuri enabled (RN-FW-01 to RN-FW-04).
7. **SSH.** `robertdebock.openssh` with the contract's settings: key only, no root login, no passwords, `ssh_port` (RN-SSH-01, RN-SSH-03, RN-ACC-05). It runs last among the configuration steps, because it also closes root SSH, which a VPS build may still be using.
8. **Report.** `/etc/raw-node/raw-node.conf`, the report script and the first-boot unit that writes `/var/lib/raw-node/confirmation.yml` (RN-REP-01).
9. **Reboot.** `ansible.builtin.reboot`, which proves the firewall is in force before the network (RN-FW-04) and lets the first-boot unit write the confirmation. Then `ansible.builtin.fetch` brings the confirmation back.
10. **Validate.** Checks inside the node with ordinary modules, and checks from the controller host over SSH as `initial_username` with the key, the way the orchestration controller will connect. RN-ACC-04 and RN-ACC-06 are checked by proxy, and RN-ACC-08 is met by procedure, since uc-raw-node never holds the password.
11. **Hand off.** The confirmation is copied unchanged to `records/<hostname>/`, and the attempt is marked `confirmed`.

As a playbook outline:

```yaml
- name: Reach the node
  hosts: localhost
  tasks:
    - ansible.builtin.include_role:
        name: "raw_node_transport_{{ raw_node_platform.transport }}"

- name: Bootstrap
  hosts: raw_node
  gather_facts: false
  roles:
    - robertdebock.bootstrap

- name: Converge to the contract
  hosts: raw_node
  gather_facts: true
  roles:
    - role: robertdebock.epel
      when: ansible_facts['os_family'] == 'RedHat'
    - raw_node_packages
    - raw_node_accounts
    - raw_node_firewall
    - robertdebock.openssh
    - raw_node_report

- name: Confirm
  hosts: localhost
  tasks:
    - ansible.builtin.include_role:
        name: raw_node_validator
    - ansible.builtin.include_tasks: tasks/write_confirmation.yml
```

## Roles

| Role | Used | Why |
| :-- | :-- | :-- |
| `robertdebock.bootstrap` | Yes | Python and `sudo`. Uses `raw` only on a node without them, once, and is idempotent. Needs a connection as root. |
| `robertdebock.epel` | Yes, RHEL family | Makes Foomuuri installable |
| `robertdebock.openssh` | Yes | Idempotent, validates with `sshd -t`. Its defaults allow root login and passwords, so the contract's settings override them. It needs `community.general`. |
| `robertdebock.users` | Optional | Three ordinary tasks do the same for one user |
| `robertdebock.firewall` | No | Installs `ufw` on Debian with a default of `allow`, which breaks RN-FW-02 and RN-FW-03. The firewall is uc-raw-node's own role. |
| `fail2ban`, `docker`, `libvirt` | No | Add their own nftables tables and forwarding, which break the firewall clauses |
| `update`, `auto_update`, `ntp`, `locale`, `cron`, `grub`, `buildtools`, `python_pip`, `software` and the rest | No | Outside the contract. They belong to onboarding or normalization. |

Roles and collections are pinned to exact versions in a `requirements.yml`.

## Secrets

Templates are code: they live in the repository, hold no secret and no example secret, and are reviewed like any other code. Anything rendered with a secret in it lands only under `~/.secrets/uc-raw-node/`: node definitions in `inputs/`, and anything rendered for a build in `<hostname>/`, with mode `0600` in directories of mode `0700`. Rendered secrets are deleted when the build ends. Records, reports and logs hold public data only, and stay out of `~/.secrets`.

## What carries over from the current repository

The registry, input checking, output paths and secrets checks, attempt records and history, failure handling, the Incus transport's launch, ownership marker and teardown, `destroy.yml`, the stand-in Incus client, `tools/check.sh` and the git hooks.

## Open points

- **Reruns.** To be idempotent, a rerun against an instance carrying uc-raw-node's ownership marker must converge it, instead of being refused as an existing instance. Only an unmarked instance is refused.
- **Failure handling across plays.** The current block and rescue live inside one play. With several plays, failure handling has to run in a final play, or the build has to be split so that one play owns the rescue.
- **`community.general`.** The Incus connection plugin and `robertdebock.openssh` both need it, so the rule of using ansible-core modules only becomes ansible-core plus pinned `community.general`.
- **The report.** Python is ensured by the bootstrap step, so the report can be written in Python, or in shell to stay independent of it.
- **`robertdebock.openssh` and keyboard-interactive.** Its Debian template sets `ChallengeResponseAuthentication` but not `KbdInteractiveAuthentication`. The validator's `sshd -T` check decides whether a template override is needed.

## Related repositories

- uc-contracts: `https://github.com/steelcj/uc-contracts`, the raw node contract
- uc-raw-node: `https://github.com/steelcj/uc-raw-node`, the controller
- `robertdebock.bootstrap`: `https://github.com/robertdebock/ansible-role-bootstrap`
- `robertdebock.epel`: `https://github.com/robertdebock/ansible-role-epel`
- `robertdebock.openssh`: `https://github.com/robertdebock/ansible-role-openssh`

## Changes

### v0.1.0

- First version, from the decisions of 2026-11-22: the contract as the only link, the minimal node definition, the split between the transport and plain Ansible, the order of operations, root during the build and password `sudo` at handover, secrets in `~/.secrets`, and the roles used and left out.
