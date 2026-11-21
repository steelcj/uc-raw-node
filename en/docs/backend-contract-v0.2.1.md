---
title: "uc-raw-node Backend Contract"
version: "0.2.0"
date: 2026-11-20
author: "Christopher Steel"
status: "Draft, not yet applied to a second backend"
description: "What every backend of the raw node controller must accept, do and return so that Ventoy, Incus and later backends all hand the orchestration controller the same raw node."
---

# uc-raw-node Backend Contract

## Purpose

Nodes pass through two controllers. The raw node controller, uc-raw-node, creates a node that meets the raw node contract and stops there. The orchestration controller takes over from the node's `confirmation.yml` and brings it to its final role. Either controller may use Ansible. What separates them is the contract, not the tool.

A backend is one way the raw node controller delivers a raw node to one kind of platform. Ventoy is the first backend and covers metal and virtual machines. Incus is the second. This document defines what any backend must do, so that a node from any backend is indistinguishable from the others when the orchestration controller reaches it.

The raw node itself is defined in `raw-node-baseline.md`, requirements RN-01 to RN-12. This document does not repeat those requirements. It defines how a backend is held to them.

## Controller types

```text
┌─────────────────────────────┐     ┌─────────────────────────────────┐
│ RAW NODE CONTROLLER         │     │ ORCHESTRATION CONTROLLER        │
│ uc-raw-node                 │     │                                 │
│                             │     │ Discovery → Verification →      │
│ Creates raw node.           │────▶│ Onboarding → Normalization →    │
│ Meets RN-* clauses.         │     │ Customization                   │
│ Writes confirmation.yml.    │     │                                 │
└─────────────────────────────┘     └─────────────────────────────────┘
```

### Raw node controller

Creates the node and meets RN-01 to RN-12 through one of its backends. Its last act is the node writing `confirmation.yml` at first boot. It never configures anything beyond the raw node.

### Orchestration controller

Runs its stages in order, one playbook each:

| Playbook | Stage | Work |
| --- | --- | --- |
| `00_discover.yml` | Discovery | Find nodes and read their `confirmation.yml` |
| `05_verify.yml` | Verification | Check the RN clauses on the node |
| `10_onboard.yml` | Onboarding | Make the node manageable |
| `20_normalize.yml` | Normalization | Apply minimal generic configuration common to every node |
| `30_customize.yml` | Customization | Apply role-specific configuration, for example `uc_openbao` |

The orchestration controller is defined in its own documents. It appears here only because it is the consumer of everything a backend produces.

## Terms

### Raw node

A freshly installed system that meets RN-01 to RN-12 and nothing more: root password, the initial user with sudo, SSH with key and password authentication for that user, the bootstrap firewall and the first-boot report.

### Contract

The pair of files at the boundary of the raw node controller. `raw-node-input.yml` goes in, `confirmation.yml` comes out. Everything between them belongs to the backend.

### Backend

The code and documents that turn `raw-node-input.yml` into a raw node on one platform, for example `backends/ventoy/` and `backends/incus/`.

### Reference node

The node that every other node's canonical files are compared against. Debian 13 on metal, delivered by the Ventoy backend.

## The contract

### Input

A backend accepts `raw-node-input.yml` exactly as the baseline defines it, with four keys and no others.

| Key | Requirement |
| --- | --- |
| `root_password_hash` | RN-03 |
| `initial_username` | RN-04 With sudo |
| `initial_password_hash` | RN-04 |
| `ssh_public_key` | RN-05 |

### Output

Each node writes `/var/lib/raw-node/confirmation.yml` once at first boot, keyed by hostname, with values measured on the node.

```yaml
deb13-ic-a1b2:
  timestamp: 2026-11-20T15:30:00-05:00
  ip: 192.0.2.20
  ip6:
  user: initial
  sudo: true
```

## Backend requirements

| ID | Requirement |
| --- | --- |
| RB-01 | Accept `raw-node-input.yml` as the only user input that describes the node. Settings that only concern the platform, such as an ISO path, an Incus image or an Incus project, go in the backend's own configuration and never in `raw-node-input.yml`. |
| RB-02 | Validate the input before changing anything, and reject missing, malformed or dummy values with the same rules as `bin/build`. |
| RB-03 | Install the canonical files from `shared/` byte for byte with the modes listed in the baseline. A backend never keeps its own copy of a canonical file. |
| RB-04 | Meet RN-01 to RN-12 as written. If a platform cannot meet a requirement, the requirement is reviewed in the baseline rather than worked around in the backend. |
| RB-05 | Apply the hostname rule, `<prefix>-<backend>-<mac4>`, using the backend's registered two-letter code (see [Backends](#backends)). |
| RB-06 | Run `raw-node-firstboot` at first boot so that the node writes its own `confirmation.yml`. The backend never writes or edits the report. |
| RB-07 | Make the report available to discovery. At minimum it is shown at the console login prompt and by `sudo raw-node-report`. Where the platform allows it, the backend also lets the report be fetched without logging in. |
| RB-08 | Configure nothing beyond the raw node. No extra packages, services, users or firewall rules. Onboarding, normalization and customization belong to the orchestration controller. |
| RB-09 | Pass the RN checks that `05_verify.yml` runs, with `sha256sum` output for the canonical files identical to the reference node. |
| RB-10 | Have one backend document listing its platforms and distributions, a coverage table with one row per RN saying how the backend meets it, any checks specific to the backend, and its status. |

## What a backend decides

A backend chooses how the raw node is delivered: installer answer files, cloud-init user data, an image build or anything else that meets the requirements, including Ansible run against the platform. It chooses which platforms and distributions it supports, and records each one in its document only once verification passes.

## Backends

| Backend | Code | Platforms | Delivery | Report retrieval | Status |
| --- | --- | --- | --- | --- | --- |
| Ventoy | `vt` | Metal, VM | Preseed and Subiquity autoinstall answer files on the Ventoy stick | Console and `sudo raw-node-report` | Working for Debian 13, Ubuntu 24.04 and Ubuntu 26.04 |
| Incus | `ic` | VM, container | cloud-init user data on a cloud image (`images:debian/13/cloud` and equivalents) | `incus file pull <instance>/var/lib/raw-node/confirmation.yml` | Planned |

### Incus notes

Incus cloud images run cloud-init, so the Incus backend can reuse `shared/cloud-init/99-raw-node.cfg` and pass the rest through the instance's `cloud-init.user-data` key. There is no installer, so RN requirements met by preseed or autoinstall settings on Ventoy have to be met by cloud-init modules instead. The coverage table in the Incus backend document records each one.

These points need checking before containers are listed as supported:

- whether the bootstrap `nftables` ruleset loads and behaves the same inside an unprivileged container's network namespace
- whether the MAC-derived suffix is stable enough to use, since Incus assigns container MAC addresses itself
- whether RN requirements that assume a kernel or boot loader the node owns need a container exception, which would be reviewed in the baseline as RB-04 requires

## Handover

The handover is the same for every backend. `00_discover.yml` reads `confirmation.yml`: the top-level key becomes the inventory host, `ip` becomes `ansible_host` and `user` becomes `ansible_user`. `05_verify.yml` then checks the RN clauses on the node itself rather than trusting the report. The orchestration controller never needs to know which backend produced a node.

## Open decisions

- Whether uc-ventoy is folded into the uc-raw-node repository as `backends/ventoy/`, or stays a separate repository that uc-raw-node depends on.
- Whether the backend code in the hostname (`vt`, `ic`) is the right place to record where a node came from, or whether it belongs only in `/etc/raw-node/raw-node.conf`.
- Whether the baseline acceptance checks are rewritten as `05_verify.yml`, so that the RN checks exist in one place.

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.2.0 | 2026-11-20 | Replaces "Ansible" as the name of the second controller with the orchestration controller and its five stages. RB-07, RB-08 and RB-09 now point at discovery, the later stages and `05_verify.yml`. Adds Controller types. |
| 0.1.0 | 2026-11-20 | First draft. Names the pre-contract controller uc-raw-node and defines RB-01 to RB-10. |
