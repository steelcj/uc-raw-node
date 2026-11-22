# Spinning Up a Debian 13 Incus Container with uc-raw-node

- **Version:** 0.1.0
- **Date:** 2026-11-22
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## What this guide covers

This guide takes a workstation or server from nothing to a Debian 13 container on a local Incus server, built through uc-raw-node's pipeline, and then tears it down again. It is the priority 1 platform, `incus_container_default`: the `adopt` strategy, the `incus_exec` transport and the image `images:debian/13`.

It is written for uc-raw-node `v0.3.0`. At that release the controller's pipeline works end to end, but the payload and the validator are placeholders. That shapes what you get:

| Step | What happens at `v0.3.0` |
| :-- | :-- |
| `validate.yml` with your own input | Checks the registry, your contract input and the platform. Creates nothing. |
| `build.yml` with your own input | Stops at the payload placeholder with "not implemented yet", before any container is launched. The attempt ends `aborted`, with a failure record. |
| `tests/build.yml`, the test wrapper | Launches a real Debian 13 container through the whole pipeline (launch, ownership marker, payload delivery, address report, confirmation), with a stand-in payload and validation skipped |
| `tests/destroy.yml` | Tears that container down by hostname, checking the ownership marker first |

The container from the test wrapper is a plain Debian 13 container, not a raw node. It has no initial user, SSH server or firewall, because the stand-in payload only proves that delivery works. Once the payload and validator land (see *Raw Node Contract Alignment*, `en/docs/design/raw-node-contract-alignment-v0.1.0.md`), `build.yml` with your own input becomes the way to build a real raw node, and this guide's build step changes accordingly.

Allow about 30 minutes on a host without Incus, most of it for the first image download. On a host that already runs Incus, about 10 minutes.

## Before you start

| Item | Requirement |
| :-- | :-- |
| Host | Debian 13, Ubuntu 24.04 or later, or Linux Mint 22, with `sudo` |
| Incus | 6.0 or later. Debian 13 has native packages. |
| Network | Outbound internet access for the image server and Python packages |
| Tools | `git`, Python 3 with `venv`, and `mkpasswd` from the `whois` package |
| SSH key | An SSH key pair on the workstation. Only the public key goes into the contract input. |

Everything runs on the host that runs Incus. uc-raw-node drives Incus through the local `incus` client, so it needs no inventory and no SSH access to the container.

## Install and initialise Incus

Skip this section if `incus info` already works for your user.

### Install the packages

On Debian 13, Incus is packaged natively. Debian's packages track the Incus LTS releases <a id="cite-incus-installing"></a>[(Linux Containers, n.d.-a)](#ref-incus-installing):

```sh
sudo apt update
sudo apt install incus
```

On Ubuntu 24.04 and Linux Mint 22, the distribution's `incus` package is a 0.x release, older than this guide needs. Use the Zabbly packages that the Incus installation guide describes instead.

### Initialise the daemon

Incus has to be configured once before it can create instances <a id="cite-debian-wiki-incus"></a>[(Debian Wiki, n.d.)](#ref-debian-wiki-incus). The minimal setup applies the default options without asking, which gives a storage pool, the `incusbr0` bridge with DHCP and a `default` profile that attaches containers to it, all this guide needs <a id="cite-incus-initialize"></a>[(Linux Containers, n.d.-b)](#ref-incus-initialize):

```sh
sudo incus admin init --minimal
```

Run `sudo incus admin init` without `--minimal` instead if you want to choose the storage backend or the bridge's address range.

### Give your user access

uc-raw-node creates a project and launches instances in it, so your user needs the `incus-admin` group:

```sh
sudo usermod -aG incus-admin "$USER"
```

Log out and back in, or run `newgrp incus-admin` in the terminal you will use. Membership of `incus-admin` gives full control of the Incus daemon through its local socket <a id="cite-debian-wiki-incus-admin"></a>[(Debian Wiki, n.d.)](#ref-debian-wiki-incus), which is as much as root on the host. Only add users you would trust with that.

### Check it works

```sh
incus info | head -5
incus network list
incus profile show default
```

`incus network list` should show `incusbr0` as managed, and the `default` profile should have an `eth0` device on `incusbr0` and a root disk.

## Create a project for uc-raw-node

Do all of this guide's work in its own Incus project, so that nothing the controller does can touch your other instances:

```sh
incus project create uc-raw-node-test -c features.images=false -c features.profiles=false
```

The two options make the project share the `default` project's images and profiles, so the `default` profile and its network work in it unchanged. Every command below passes the project, and the controller never deletes anything outside the project it is given.

The transport's own default project is `default`. Always pass `-e raw_node_incus_project=uc-raw-node-test`, as the commands below do.

## Install Ansible

uc-raw-node is tested on ansible-core 2.21.6. Install it in a virtual environment, so it does not depend on the distribution's Ansible package:

```sh
python3 -m venv ~/.venvs/ansible
~/.venvs/ansible/bin/pip install 'ansible-core==2.21.6' ansible-lint
. ~/.venvs/ansible/bin/activate
ansible-playbook --version | head -1
```

Activate the environment (`. ~/.venvs/ansible/bin/activate`) in every new terminal before running the playbooks below.

## Get uc-raw-node

```sh
git clone https://github.com/steelcj/uc-raw-node.git
cd uc-raw-node
git checkout v0.3.0
```

Tell the repository's checks where Ansible is, so they work outside the activated environment too, including from git hooks:

```sh
printf '%s\n' 'PATH="$HOME/.venvs/ansible/bin:$PATH"' > tools/check.env
tools/install-hooks.sh
tools/check.sh --fast
```

`tools/check.env` is ignored by git. The fast check takes a few seconds and should end with every step passed. Run every command in the rest of this guide from the repository root.

## Write your contract input

The contract input describes the node: its hostname, the two password hashes, the initial user and the SSH public key. It holds password hashes, so keep it out of the repository. The controller's secrets path, `~/.secrets/uc-raw-node`, is a good place, and it must not be readable by anyone else. The controller stops if that directory gives any access to group or others:

```sh
(umask 077 && mkdir -p ~/.secrets/uc-raw-node/inputs)
```

Make the two hashes. `mkpasswd` asks for each password and prints its hash:

```sh
mkpasswd --method=yescrypt   # root password
mkpasswd --method=yescrypt   # initial user's password
```

The root password belongs to you as the producer, and nothing later needs it. The initial user's password is what the orchestration controller will use at the console and for `sudo`, and the raw node contract requires it to be at least 15 characters (RN-ACC-08). Keep both in your password manager. Only the hashes go into the file.

Write the file, replacing the placeholders with your two hashes and the single line from your `~/.ssh/<key>.pub`:

```sh
cat > ~/.secrets/uc-raw-node/inputs/deb13-ic-01.yml <<'EOF'
hostname: deb13-ic-01
root_password_hash: "PASTE_ROOT_HASH_HERE"
initial_username: initial
initial_password_hash: "PASTE_INITIAL_HASH_HERE"
ssh_public_key: "PASTE_PUBLIC_KEY_LINE_HERE"
EOF
chmod 600 ~/.secrets/uc-raw-node/inputs/deb13-ic-01.yml
```

The quoted `'EOF'` stops the shell from expanding the `$` signs in the hashes. The hostname must be a single lowercase DNS label, and it becomes the container's name. The user name must not be `root`. Both password fields must be crypt hashes; plaintext is refused.

## Validate

Check the registry, the input and the platform without building anything:

```sh
ansible-playbook validate.yml \
  -e @$HOME/.secrets/uc-raw-node/inputs/deb13-ic-01.yml \
  -e target_platform=incus_container_default
```

It should finish without failures. If a field is wrong, the message names it, and nothing has been created. Fix the file and run it again.

## Run a real build

```sh
ansible-playbook build.yml \
  -e @$HOME/.secrets/uc-raw-node/inputs/deb13-ic-01.yml \
  -e target_platform=incus_container_default \
  -e raw_node_incus_project=uc-raw-node-test \
  -e raw_node_incus_image=images:debian/13
```

At `v0.3.0` this run fails on purpose. The checks pass, the output paths and the attempt record are written, and then the payload step stops with "not implemented yet". That is before the transport runs, so no container is launched, and failure handling ends the attempt as `aborted`:

```sh
cat records/deb13-ic-01/attempt.yml
cat records/deb13-ic-01/failure.yml
incus list --project uc-raw-node-test
```

`attempt.yml` shows `state: aborted`, `failure.yml` names the failed step and `action: abort`, and `incus list` shows no instance. An `aborted` attempt does not block the next build for the same hostname. Once the payload exists, this command builds the raw node.

## Spin up a container with the test wrapper

The test wrapper runs `build.yml` itself, unchanged, with two test-only overrides: a stand-in payload, and validation skipped. It uses the test fixture's input (hostname `rn-test-incus-exec`, fake hashes and key), and writes everything under `artifacts/` rather than `records/`, `reports/` and `logs/`:

```sh
ansible-playbook -i localhost, -c local tests/build.yml \
  -e raw_node_test_scenario=success \
  -e raw_node_incus_project=uc-raw-node-test \
  -e raw_node_incus_image=images:debian/13
```

The first run downloads the Debian 13 image, which takes a minute or two. After that a build takes under 20 seconds. The pipeline launches the container with its ownership marker, waits for its address, pushes and runs the stand-in payload, reports the address and writes the confirmation.

Look at what it built:

```sh
incus list --project uc-raw-node-test
incus exec rn-test-incus-exec --project uc-raw-node-test -- cat /etc/os-release
incus config get rn-test-incus-exec user.uc-raw-node.created --project uc-raw-node-test
cat artifacts/records/rn-test-incus-exec/attempt.yml
cat artifacts/reports/rn-test-incus-exec/report.yml
cat artifacts/logs/rn-test-incus-exec/incus_exec-run.log
```

You should see:

- a running container, `rn-test-incus-exec`, with an IPv4 address and usually a global IPv6 address from `incusbr0`;
- Debian 13 (trixie) in `/etc/os-release`;
- `true` for the ownership marker, which is how the controller later recognises a container it created;
- `state: confirmed` in the attempt record;
- the addresses in the report, with an empty `ssh_host_keys` list, because the image has no SSH server;
- the stand-in payload's single line in the run log.

You can get a shell in the container with `incus exec rn-test-incus-exec --project uc-raw-node-test -- bash`. Remember that it is not a raw node: nothing the raw node contract promises has been set up in it.

## Tear it down

Destroy the container by hostname. The test wrapper for `destroy.yml` reads the attempt record under `artifacts/`:

```sh
ansible-playbook -i localhost, -c local tests/destroy.yml \
  -e hostname=rn-test-incus-exec \
  -e raw_node_incus_project=uc-raw-node-test
incus list --project uc-raw-node-test
cat artifacts/records/rn-test-incus-exec/attempt.yml
```

The container is gone, and the attempt record says `destroyed`. The records are kept, so the node's history survives its teardown.

The transport deletes only a container that carries its ownership marker for that hostname. If you launched a container by hand under the same name, the teardown refuses it and leaves it alone.

When you are finished with the guide, you can leave the empty project for the next run, or remove it with `incus project delete uc-raw-node-test`. A project must be empty before Incus deletes it.

## Troubleshooting

| Symptom | Likely cause and fix |
| :-- | :-- |
| `permission denied` on the Incus socket | Your user is not in `incus-admin` yet in this session. Log out and back in, or run `newgrp incus-admin`. |
| `ansible-playbook: command not found` | The virtual environment is not active. Run `. ~/.venvs/ansible/bin/activate`. For `tools/check.sh` and the hooks, check `tools/check.env`. |
| The secrets path "gives access to group or others" | `~/.secrets/uc-raw-node` or a node's directory under it is not mode `0700`. Run `chmod 700` on it, as the message says. Nothing was created. |
| The build waits, then fails with no address | The container got no address from `incusbr0`. Check `incus network show incusbr0` for DHCP, and check the host's firewall: Docker and some firewall managers drop forwarded traffic from Incus bridges. |
| The build refuses to start because the attempt is `confirmed`, `quarantined`, `in_progress` or `failed` | A node may still exist for that hostname. Destroy it first, or pass `-e raw_node_attempt_replace=true` if you know it is gone. |
| The transport refuses an existing instance | A container with that name exists but was not created by uc-raw-node. Pick another hostname, or remove that container yourself. |
| The teardown refuses the container | It has no ownership marker for that hostname, so uc-raw-node did not create it. Delete it by hand if you are sure. |
| `aborted` after `build.yml` with your own input | Expected at `v0.3.0`: the payload is a placeholder. See Run a real build. |

## What changes when the payload lands

Once uc-raw-node has its payload and validator, `build.yml` with your own input launches the container, installs the node files, restarts it so the firewall comes up before the network, and validates the node against the raw node contract. The confirmation in `records/deb13-ic-01/` is then the node's own, with its addresses, users, host keys and firewall, ready for the orchestration controller. The test wrapper stays for testing the pipeline, and this guide's build and teardown steps move to `build.yml` and `destroy.yml` with your own input.

## Changes

### v0.1.0

- First version, for uc-raw-node `v0.3.0`: Incus setup, a dedicated project, Ansible in a virtual environment, the contract input in the secrets path, `validate.yml`, a real build that ends `aborted` at the payload placeholder, a container spun up through the test wrapper, teardown and troubleshooting.

## References

<a id="ref-debian-wiki-incus"></a>Debian Wiki. (n.d.). *Incus*. Retrieved November 22, 2026, from https://wiki.debian.org/Incus
[Return to citation](#cite-debian-wiki-incus)

<a id="ref-incus-installing"></a>Linux Containers. (n.d.-a). *How to install Incus*. Incus documentation. Retrieved November 22, 2026, from https://linuxcontainers.org/incus/docs/main/installing/
[Return to citation](#cite-incus-installing)

<a id="ref-incus-initialize"></a>Linux Containers. (n.d.-b). *How to initialize Incus*. Incus documentation. Retrieved November 22, 2026, from https://linuxcontainers.org/incus/docs/main/howto/initialize/
[Return to citation](#cite-incus-initialize)
